"""
ledgerflow_daily_dag.py — Full medallion pipeline orchestrated by Airflow.

What this DAG does (in order):
  1. generate_data     — run Faker generators for customers, accounts, loans
  2. load_paysim       — convert PaySim CSV into transactions.csv (idempotent)
  3. load_bronze       — ingest all 4 CSVs into bronze schema (DuckDB / RDS)
  4. validate_bronze   — run GX bronze checkpoint; fail-fast if rules break
  5. run_dbt_staging   — build silver staging views via dbt
  6. validate_silver   — run GX silver checkpoint
  7. run_dbt_marts     — build gold dimension and fact tables via dbt
  8. run_dbt_tests     — run all 48 dbt tests; fail if any break

Why this order matters (medallion gating):
  Bronze gate  (step 4)  — bad upstream data never reaches silver
  Silver gate  (step 6)  — dbt transformation bugs never reach gold
  Gold tests   (step 8)  — final integrity check before dashboard reads

Schedule: daily at 06:00 UTC (data lands overnight, pipeline runs at dawn).

How to trigger manually in the Airflow UI:
  DAGs -> ledgerflow_daily_pipeline -> Trigger DAG

Environment variables read at runtime:
  REPO_ROOT    — absolute path to the repo (default: /opt/airflow/repo)
  DB_ENGINE    — "duckdb" (local) or "postgres" (prod)
  DUCKDB_PATH  — path to ledgerflow.duckdb when DB_ENGINE=duckdb
  DATABASE_URL — postgres connection string when DB_ENGINE=postgres
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# ── Default args applied to every task ──────────────────────────────────────
# retries=1   : re-run once on failure (transient network blip, disk flush)
# retry_delay : wait 5 min before retry so a transient error has time to clear
# email_on_failure: set True in prod and add your email to 'email' list

DEFAULT_ARGS = {
    "owner": "ledgerflow",
    "depends_on_past": False,
    "start_date": datetime(2026, 5, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# ── Paths — read from env so the same DAG works locally and on ECS ──────────
REPO_ROOT = os.getenv("REPO_ROOT", "/opt/airflow/repo")
PYTHON    = os.getenv("PIPELINE_PYTHON", "python")   # override with conda env python in ECS

# Shared env passed to every BashOperator task
TASK_ENV = {
    "DB_ENGINE":    os.getenv("DB_ENGINE", "duckdb"),
    "DUCKDB_PATH":  os.getenv("DUCKDB_PATH", f"{REPO_ROOT}/ledgerflow.duckdb"),
    "DATABASE_URL": os.getenv("DATABASE_URL", ""),
    "REPO_ROOT":    REPO_ROOT,
}

# ── DAG definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="ledgerflow_daily_pipeline",
    default_args=DEFAULT_ARGS,
    description="LedgerFlow: Bronze -> Silver -> Gold medallion pipeline",
    schedule_interval="0 6 * * *",   # 06:00 UTC daily
    catchup=False,                    # don't backfill missed runs
    max_active_runs=1,                # prevent concurrent runs from overlapping writes
    tags=["ledgerflow", "pipeline", "medallion"],
) as dag:

    # ── STEP 1: Generate Faker data (customers, accounts, loans) ────────────
    # Idempotent: overwrites data/raw/*.csv — safe to re-run
    generate_data = BashOperator(
        task_id="generate_data",
        bash_command=(
            f"cd {REPO_ROOT} && "
            f"{PYTHON} data_generator/generate_customers.py && "
            f"{PYTHON} data_generator/generate_accounts.py && "
            f"{PYTHON} data_generator/generate_loans.py"
        ),
        env=TASK_ENV,
        doc_md="""
        **Generate synthetic customer, account, and loan data using Faker.**

        Writes to `data/raw/customers.csv`, `accounts.csv`, `loans.csv`.
        Always overwrites — each run produces a fresh snapshot.
        Transactions use PaySim (real dataset), not Faker.
        """,
    )

    # ── STEP 2: Prepare PaySim transactions ─────────────────────────────────
    # load_paysim.py is idempotent: checks if transactions.csv already exists
    # and skips re-conversion if the source CSV hasn't changed.
    load_paysim = BashOperator(
        task_id="load_paysim",
        bash_command=(
            f"cd {REPO_ROOT} && "
            f"{PYTHON} data_generator/load_paysim.py"
        ),
        env=TASK_ENV,
        doc_md="""
        **Convert raw PaySim CSV to warehouse-schema transactions.csv.**

        Source: `data/raw/PS_20174392719_1491204439457_log.csv` (470 MB).
        Output: `data/raw/transactions.csv` (6.36M rows, ~1.2 GB).

        PaySim gives us real fraud patterns — 8,213 fraud transactions (0.129%)
        concentrated in CASH_OUT and TRANSFER types.
        """,
    )

    # ── STEP 3: Load bronze layer ────────────────────────────────────────────
    # Drops and recreates all bronze tables (idempotent full-refresh).
    # In production you would switch to append-only with dedup logic.
    load_bronze = BashOperator(
        task_id="load_bronze",
        bash_command=(
            f"cd {REPO_ROOT} && "
            # Drop existing bronze tables first to avoid duplicate rows
            f"{PYTHON} -c \""
            f"import duckdb; con=duckdb.connect('{REPO_ROOT}/ledgerflow.duckdb'); "
            f"[con.execute(f'DROP TABLE IF EXISTS bronze.{{t}}') "
            f"for t in ['transactions','customers','accounts','loans']]; "
            f"con.close()\""
            f" && {PYTHON} ingestion/load_bronze.py"
        ),
        env=TASK_ENV,
        doc_md="""
        **Ingest all 4 source CSVs into the bronze schema.**

        Uses DuckDB's native Python API (not chunked SQLAlchemy) so 6.36M rows
        load in ~3 seconds. Adds audit columns: _loaded_at, _source_file, _batch_id.
        Schema drift detection runs before any row lands — aborts on missing columns.
        """,
    )

    # ── STEP 4: Great Expectations bronze checkpoint ─────────────────────────
    # Exit code 1 = at least one expectation failed -> Airflow marks task FAILED
    # -> downstream tasks (dbt) are skipped. This is the key quality gate.
    validate_bronze = BashOperator(
        task_id="validate_bronze",
        bash_command=(
            f"cd {REPO_ROOT}/great_expectations && "
            f"{PYTHON} run_validations.py bronze"
        ),
        env=TASK_ENV,
        doc_md="""
        **Run GX bronze checkpoint (23 rules on raw transactions, 13 on customers).**

        Checks: null PKs, duplicate transaction_ids, valid transaction types,
        amount range 0-100M, row count 1K-10M, mean amount 50K-500K.

        Exit 1 on failure -> Airflow blocks all downstream tasks.
        This prevents bad upstream data from poisoning silver and gold.
        """,
    )

    # ── STEP 5: dbt staging models (silver layer) ───────────────────────────
    # --select staging runs only the 4 stg_* views, not the marts.
    # This is faster and isolates the silver gate.
    run_dbt_staging = BashOperator(
        task_id="run_dbt_staging",
        bash_command=(
            f"cd {REPO_ROOT}/dbt_ledgerflow && "
            f"dbt run --profiles-dir . --select staging"
        ),
        env=TASK_ENV,
        doc_md="""
        **Build silver staging views: stg_transactions, stg_customers,
        stg_accounts, stg_loans.**

        These are SQL views (no data copied) that cast, trim, and filter
        the bronze tables. Key transformation: derive `is_missed_fraud`
        (fraud transactions not caught by the flagging system).
        """,
    )

    # ── STEP 6: Great Expectations silver checkpoint ─────────────────────────
    validate_silver = BashOperator(
        task_id="validate_silver",
        bash_command=(
            f"cd {REPO_ROOT}/great_expectations && "
            f"{PYTHON} run_validations.py silver"
        ),
        env=TASK_ENV,
        doc_md="""
        **Run GX silver checkpoint (12 rules on stg_transactions).**

        Checks: null PKs, unique transaction IDs, valid types and currency,
        amount range, row count after dbt filtering.

        Catches transformation bugs — e.g., a bad WHERE clause in stg_transactions
        that accidentally drops all TRANSFER rows.
        """,
    )

    # ── STEP 7: dbt marts (gold layer) ──────────────────────────────────────
    # --select marts+ runs dim_*, fact_* and intermediate models
    run_dbt_marts = BashOperator(
        task_id="run_dbt_marts",
        bash_command=(
            f"cd {REPO_ROOT}/dbt_ledgerflow && "
            f"dbt run --profiles-dir . --select marts intermediate"
        ),
        env=TASK_ENV,
        doc_md="""
        **Build gold layer: dim_customer (SCD2), dim_account, dim_product,
        int_customer_accounts, fact_transactions, fact_fraud_alerts.**

        fact_transactions: 6.36M rows, star schema with FK surrogate keys.
        fact_fraud_alerts: fraud/flagged subset with TRUE/FALSE POSITIVE/NEGATIVE labels.
        dim_customer: SCD Type 2 — new row per change, valid_from/valid_to/is_current.
        """,
    )

    # ── STEP 8: dbt tests ───────────────────────────────────────────────────
    run_dbt_tests = BashOperator(
        task_id="run_dbt_tests",
        bash_command=(
            f"cd {REPO_ROOT}/dbt_ledgerflow && "
            f"dbt test --profiles-dir ."
        ),
        env=TASK_ENV,
        doc_md="""
        **Run all 48 dbt tests across silver and gold models.**

        Covers: not_null, unique, accepted_values, custom SCD2 overlap check,
        custom no-negative-amounts check.

        Exit 1 on any failure -> Airflow marks the run FAILED.
        The Vercel dashboard will show a red quality badge until fixed.
        """,
    )

    # ── Task dependencies (the DAG graph) ───────────────────────────────────
    #
    # generate_data ──┐
    #                 ├─> load_paysim ─> load_bronze ─> validate_bronze
    #                                                        │
    #                                                  run_dbt_staging
    #                                                        │
    #                                                  validate_silver
    #                                                        │
    #                                                  run_dbt_marts
    #                                                        │
    #                                                  run_dbt_tests
    #
    generate_data >> load_paysim >> load_bronze >> validate_bronze
    validate_bronze >> run_dbt_staging >> validate_silver
    validate_silver >> run_dbt_marts >> run_dbt_tests

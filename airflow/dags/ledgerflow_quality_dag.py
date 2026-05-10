"""
ledgerflow_quality_dag.py — On-demand Great Expectations checkpoint runner.

Why this DAG exists as a separate file:
  The daily pipeline (ledgerflow_daily_dag) runs GX as part of the full flow.
  But sometimes you want to CHECK data quality without re-running the entire
  pipeline — e.g., after a hotfix, before a quarterly audit, or when an analyst
  reports "the numbers look off today."

  This DAG lets you trigger just the GX checkpoints from the Airflow UI with
  one click, without touching any data.

Schedule: not scheduled (manual triggers only).

How to use:
  Airflow UI -> DAGs -> ledgerflow_quality_gate -> Trigger DAG w/ config
  Or via CLI: airflow dags trigger ledgerflow_quality_gate

Optional DAG run config (passed as JSON in Trigger UI):
  { "layer": "bronze" }   -- run bronze checkpoint only
  { "layer": "silver" }   -- run silver checkpoint only
  { "layer": "all" }      -- run all checkpoints (default)

Exit codes from run_validations.py:
  0 = all expectations passed
  1 = at least one expectation failed (Airflow marks task FAILED)
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

DEFAULT_ARGS = {
    "owner": "ledgerflow",
    "depends_on_past": False,
    "start_date": datetime(2026, 5, 1),
    "email_on_failure": False,
    "retries": 0,   # quality checks should not auto-retry — a failure needs human review
}

REPO_ROOT = os.getenv("REPO_ROOT", "/opt/airflow/repo")
PYTHON    = os.getenv("PIPELINE_PYTHON", "python")

TASK_ENV = {
    "DB_ENGINE":    os.getenv("DB_ENGINE", "duckdb"),
    "DUCKDB_PATH":  os.getenv("DUCKDB_PATH", f"{REPO_ROOT}/ledgerflow.duckdb"),
    "DATABASE_URL": os.getenv("DATABASE_URL", ""),
    "REPO_ROOT":    REPO_ROOT,
}

with DAG(
    dag_id="ledgerflow_quality_gate",
    default_args=DEFAULT_ARGS,
    description="On-demand GX data quality checkpoints (bronze + silver)",
    schedule_interval=None,   # manual trigger only
    catchup=False,
    max_active_runs=1,
    tags=["ledgerflow", "quality", "great-expectations"],
) as dag:

    # ── Bronze checkpoint ────────────────────────────────────────────────────
    # 23 rules: null checks, uniqueness, accepted values, amount range,
    # mean distribution, row count, column presence, regex formats
    validate_bronze = BashOperator(
        task_id="validate_bronze",
        bash_command=(
            f"cd {REPO_ROOT}/great_expectations && "
            f"{PYTHON} run_validations.py bronze"
        ),
        env=TASK_ENV,
        doc_md="""
        **Bronze checkpoint: 23 expectations on raw PaySim transactions
        and 13 on raw customers.**

        Key rules:
        - transaction_id, account_id, customer_id, amount must not be null
        - transaction_id must be unique (no duplicate loads)
        - transaction_type in [CASH_OUT, PAYMENT, CASH_IN, TRANSFER, DEBIT]
        - amount between 0 and 100,000,000 (PaySim mobile-money scale)
        - mean amount between 50,000 and 500,000 (distribution guard)
        - row count between 1,000 and 10,000,000

        Data Docs report is written to:
        great_expectations/uncommitted/data_docs/local_site/index.html
        """,
    )

    # ── Silver checkpoint ────────────────────────────────────────────────────
    # 12 rules: verifies the dbt staging transformations didn't break anything
    validate_silver = BashOperator(
        task_id="validate_silver",
        bash_command=(
            f"cd {REPO_ROOT}/great_expectations && "
            f"{PYTHON} run_validations.py silver"
        ),
        env=TASK_ENV,
        doc_md="""
        **Silver checkpoint: 12 expectations on stg_transactions (dbt view).**

        Key rules:
        - No nulls on PKs and fraud flags after dbt filtering
        - transaction_id unique in the cleaned view
        - transaction_type and currency match PaySim accepted values
        - amount still within 0-100M range after transformation
        - row count between 1K and 10M

        Catches dbt transformation bugs that bronze checks would miss
        (e.g., a bad CAST that turns valid amounts into NULLs).
        """,
    )

    # ── Summary report ───────────────────────────────────────────────────────
    # Runs regardless of upstream success/failure (trigger_rule=all_done)
    # so you always get a summary even when something fails.
    quality_summary = BashOperator(
        task_id="quality_summary",
        bash_command=(
            f"cd {REPO_ROOT}/great_expectations && "
            f"{PYTHON} run_validations.py all 2>&1 | tail -20"
        ),
        env=TASK_ENV,
        trigger_rule="all_done",   # run even if upstream failed
        doc_md="""
        **Print a combined summary of all checkpoint results.**

        Runs with trigger_rule=all_done so it always executes, even when
        bronze or silver failed. This gives operators a single log entry
        with pass/fail counts for all suites.
        """,
    )

    # ── Graph ────────────────────────────────────────────────────────────────
    # Bronze and silver run in parallel (they read from different schemas),
    # then summary collects both results.
    #
    #   validate_bronze ─┐
    #                    ├─> quality_summary
    #   validate_silver ─┘
    #
    [validate_bronze, validate_silver] >> quality_summary

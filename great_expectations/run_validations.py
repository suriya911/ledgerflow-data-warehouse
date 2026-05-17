"""
run_validations.py — Daily checkpoint runner (called by Airflow).

What this does:
  Loads each table from DuckDB (or Postgres in prod), runs the expectation
  suite saved by build_expectations.py, and prints a summary.

  Exit code 0 = all critical checks passed (pipeline can continue)
  Exit code 1 = critical failures detected (Airflow task fails, downstream halted)

Usage:
  python run_validations.py bronze   # run bronze checkpoints only
  python run_validations.py silver   # run silver checkpoints only
  python run_validations.py all      # run all checkpoints (default)

Airflow uses:
  BashOperator(bash_command="python run_validations.py bronze")
  BashOperator(bash_command="python run_validations.py silver")

Why separate bronze and silver runs?
  The Airflow DAG runs bronze checks BEFORE dbt, silver checks AFTER dbt.
  Keeping them as separate callable targets lets the DAG inject them at the
  right points in the dependency chain.

Output:
  - Console summary with pass/fail counts per suite
  - Validation results written to uncommitted/validations/ (for Data Docs)
  - HTML Data Docs rebuilt after each run (viewable in browser)
"""

import os
import sys

import great_expectations as gx
import pandas as pd
from sqlalchemy import create_engine

DB_ENGINE    = os.getenv("DB_ENGINE", "duckdb").lower()
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DUCKDB_PATH  = os.getenv(
    "DUCKDB_PATH",
    os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "ledgerflow.duckdb"))
)
POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ledger:ledger@localhost:5432/ledgerflow",
)

GX_ROOT = os.path.dirname(os.path.abspath(__file__))


def get_engine():
    if DB_ENGINE == "duckdb":
        from sqlalchemy import create_engine as _ce
        return _ce(f"duckdb:///{DUCKDB_PATH}", connect_args={"read_only": True})
    return create_engine(POSTGRES_URL)


def load_table(engine, schema: str, table: str) -> pd.DataFrame:
    return pd.read_sql(f'SELECT * FROM "{schema}"."{table}"', engine)


def run_suite(context, datasource, engine, suite_name: str, schema: str, table: str) -> dict:
    """
    Load data, run a saved expectation suite against it, return results summary.
    """
    print(f"\n  Checkpoint: {suite_name} ({schema}.{table})")

    df = load_table(engine, schema, table)
    print(f"  Rows loaded: {len(df):,}")

    asset = datasource.add_dataframe_asset(name=f"{suite_name}_run_asset")
    batch_request = asset.build_batch_request(dataframe=df)

    validator = context.get_validator(
        batch_request=batch_request,
        expectation_suite_name=suite_name,
    )

    results = validator.validate()
    stats = results["statistics"]

    passed     = stats["successful_expectations"]
    failed     = stats["unsuccessful_expectations"]
    total      = stats["evaluated_expectations"]
    success    = results["success"]

    status = "PASS" if success else "FAIL"
    print(f"  Result: {status}  |  {passed}/{total} expectations passed  |  {failed} failed")

    if not success:
        print("  Failed expectations:")
        for r in results["results"]:
            if not r["success"]:
                exp_type = r["expectation_config"]["expectation_type"]
                col      = r["expectation_config"]["kwargs"].get("column", "table-level")
                print(f"    FAIL  {exp_type}  on column: {col}")

    return {
        "suite":   suite_name,
        "success": success,
        "passed":  passed,
        "failed":  failed,
        "total":   total,
    }


# ── Checkpoint definitions ───────────────────────────────────────────────────

BRONZE_CHECKPOINTS = [
    ("bronze_transactions", "bronze", "transactions"),
    ("bronze_customers",    "bronze", "customers"),
]

SILVER_CHECKPOINTS = [
    ("silver_transactions", "main_silver", "stg_transactions"),
]


def run_checkpoints(which: str = "all") -> bool:
    """
    Run the requested checkpoints.
    Returns True if all passed, False if any failed.
    """
    print(f"=== Great Expectations — running '{which}' checkpoints ===")

    context    = gx.get_context(context_root_dir=GX_ROOT)
    engine     = get_engine()
    datasource = context.sources.add_or_update_pandas(name="pandas_runtime")

    to_run = []
    if which in ("all", "bronze"):
        to_run.extend(BRONZE_CHECKPOINTS)
    if which in ("all", "silver"):
        to_run.extend(SILVER_CHECKPOINTS)

    all_results = []
    for suite_name, schema, table in to_run:
        r = run_suite(context, datasource, engine, suite_name, schema, table)
        all_results.append(r)

    # Rebuild Data Docs so the HTML report is fresh
    context.build_data_docs()

    # Summary
    print("\n=== Summary ===")
    any_failed = False
    for r in all_results:
        icon = "OK " if r["success"] else "FAIL"
        print(f"  [{icon}] {r['suite']:35s}  {r['passed']}/{r['total']} passed")
        if not r["success"]:
            any_failed = True

    if any_failed:
        print("\nCRITICAL: One or more checkpoints failed.")
        print("Fix data quality issues before running downstream dbt models.")
    else:
        print("\nAll checkpoints passed. Pipeline may continue.")

    docs_path = os.path.join(
        GX_ROOT, "uncommitted", "data_docs", "local_site", "index.html"
    )
    print(f"Data Docs: file://{docs_path}")

    return not any_failed


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which not in ("all", "bronze", "silver"):
        print("Usage: python run_validations.py [all|bronze|silver]")
        sys.exit(1)

    success = run_checkpoints(which)
    sys.exit(0 if success else 1)

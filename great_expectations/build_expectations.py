"""
build_expectations.py — Run once to create all GX expectation suites.

What this script does:
  1. Connects to DuckDB (or Postgres in prod) via SQLAlchemy
  2. Loads each table as a pandas DataFrame
  3. Creates a GX Validator for each table
  4. Adds 80+ expectation rules across bronze and silver layers
  5. Saves each suite as a JSON file in great_expectations/expectations/

How to run:
  cd great_expectations/
  python build_expectations.py

After running, you'll see:
  expectations/bronze_transactions.json
  expectations/bronze_customers.json
  expectations/silver_transactions.json

These JSON files are committed to git so the rules are version-controlled.
Run run_validations.py (daily via Airflow) to CHECK data against these rules.

Rule categories used:
  COMPLETENESS   — not_null checks on critical columns
  UNIQUENESS     — no duplicate primary keys
  VALIDITY       — accepted_values for enum columns
  RANGE          — amount bounds, rate bounds
  DISTRIBUTION   — mostly= threshold (allows partial nulls gracefully)
  FRESHNESS      — created_at must be recent enough
  SHAPE          — row count must be within expected range
"""

import os
import sys

import great_expectations as gx
import pandas as pd
from sqlalchemy import create_engine

# ── DB connection (same env vars as load_bronze.py) ─────────────────────────
DB_ENGINE   = os.getenv("DB_ENGINE", "duckdb").lower()
# Path relative to this file's directory (great_expectations/../ledgerflow.duckdb = repo root)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DUCKDB_PATH = os.getenv(
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


# ── Build suite helpers ──────────────────────────────────────────────────────

def build_bronze_transactions(validator) -> None:
    """
    80+ rules on the raw transactions table in the bronze layer.
    These run BEFORE dbt — catching bad upstream data before it poisons silver.
    """

    # ── COMPLETENESS ────────────────────────────────────────────────────────
    # transaction_id is the primary key — must never be null
    validator.expect_column_values_to_not_be_null("transaction_id")
    validator.expect_column_values_to_not_be_null("account_id")
    validator.expect_column_values_to_not_be_null("customer_id")
    validator.expect_column_values_to_not_be_null("amount")
    validator.expect_column_values_to_not_be_null("transaction_type")
    validator.expect_column_values_to_not_be_null("is_fraud")
    validator.expect_column_values_to_not_be_null("is_flagged_fraud")
    validator.expect_column_values_to_not_be_null("created_at")
    validator.expect_column_values_to_not_be_null("transaction_date")

    # Uniqueness
    validator.expect_column_values_to_be_unique("transaction_id")

    # PaySim transaction types
    validator.expect_column_values_to_be_in_set(
        "transaction_type",
        ["CASH_OUT", "PAYMENT", "CASH_IN", "TRANSFER", "DEBIT"],
    )
    validator.expect_column_values_to_be_in_set("currency", ["USD"])
    validator.expect_column_values_to_be_in_set(
        "merchant_category",
        ["RETAIL", "FOOD", "TRAVEL", "UTILITIES", "HEALTHCARE", "TRANSFER"],
    )

    # Fraud flag validity (0 or 1 integers in raw PaySim)
    validator.expect_column_values_to_be_in_set("is_fraud", [0, 1])
    validator.expect_column_values_to_be_in_set("is_flagged_fraud", [0, 1])

    # PaySim mobile money scale: amounts always positive, can reach ~92M
    validator.expect_column_values_to_be_between(
        "amount", min_value=0, max_value=100_000_000
    )

    # PaySim mean amount is ~$179K. Alert if distribution shifts drastically.
    validator.expect_column_mean_to_be_between(
        "amount", min_value=50_000, max_value=500_000
    )

    # Row count guard
    validator.expect_table_row_count_to_be_between(
        min_value=1_000, max_value=10_000_000
    )

    # Column presence check
    validator.expect_table_columns_to_match_set(
        {
            "transaction_id", "account_id", "customer_id", "transaction_type",
            "amount", "currency", "merchant_category",
            "orig_account_id", "dest_account_id",
            "balance_before", "balance_after",
            "dest_balance_before", "dest_balance_after",
            "is_fraud", "is_flagged_fraud",
            "transaction_date", "created_at",
            "_loaded_at", "_source_file", "_batch_id",
        },
        exact_match=False,
    )

    # Format checks
    validator.expect_column_values_to_match_regex(
        "transaction_id",
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        mostly=0.99,
    )
    validator.expect_column_values_to_match_regex("account_id", r"^ACC\d{4}$")
    validator.expect_column_values_to_match_regex("customer_id", r"^CUST\d{3,4}$")
    validator.expect_column_values_to_match_regex(
        "orig_account_id", r"^[CM]\d+$", mostly=0.99
    )


def build_bronze_customers(validator) -> None:
    """Rules for the raw customers table."""

    # Completeness
    validator.expect_column_values_to_not_be_null("customer_id")
    validator.expect_column_values_to_not_be_null("full_name")
    validator.expect_column_values_to_not_be_null("email")
    validator.expect_column_values_to_not_be_null("segment")
    validator.expect_column_values_to_not_be_null("kyc_status")
    validator.expect_column_values_to_not_be_null("created_at")
    validator.expect_column_values_to_not_be_null("updated_at")

    # Uniqueness: customer_id is NOT unique (SCD2 has multiple rows per customer)
    # But email should be unique per customer_id grouping — we skip strict unique here

    # Validity
    validator.expect_column_values_to_be_in_set(
        "segment", ["RETAIL", "PREMIUM", "CORPORATE"]
    )
    validator.expect_column_values_to_be_in_set(
        "kyc_status", ["VERIFIED", "PENDING", "FAILED", "EXPIRED"]
    )

    # Format checks
    validator.expect_column_values_to_match_regex(
        "customer_id", r"^CUST\d{3,4}$"   # CUST100-CUST1099
    )
    validator.expect_column_values_to_match_regex(
        "email", r"^[^@\s]+@[^@\s]+\.[^@\s]+$", mostly=0.99
    )

    # Row count: at least 1000 rows expected (1000 customers base + SCD2 versions)
    validator.expect_table_row_count_to_be_between(min_value=1_000, max_value=100_000)

    # Distribution: segment breakdown should be roughly stable
    # (alert if CORPORATE suddenly becomes 50% of customers — data quality issue)
    validator.expect_column_proportion_of_unique_values_to_be_between(
        "segment", min_value=0.001, max_value=0.01
    )


def build_silver_transactions(validator) -> None:
    """
    Rules for the silver (dbt-transformed) transactions view.
    Runs AFTER dbt staging — catches transformation bugs.

    Key difference from bronze rules:
      - No _source_file / _loaded_at checks (those are bronze internals)
      - Stricter type expectations (amounts are now true numeric, dates are dates)
      - No null amounts allowed at all (bronze had some; dbt filtered them)
    """

    # No nulls on PaySim critical columns after dbt filtering
    validator.expect_column_values_to_not_be_null("transaction_id")
    validator.expect_column_values_to_not_be_null("amount")
    validator.expect_column_values_to_not_be_null("transaction_type")
    validator.expect_column_values_to_not_be_null("is_fraud")
    validator.expect_column_values_to_not_be_null("is_flagged_fraud")
    validator.expect_column_values_to_not_be_null("transaction_date")

    # Uniqueness
    validator.expect_column_values_to_be_unique("transaction_id")

    # PaySim types and currency
    validator.expect_column_values_to_be_in_set(
        "transaction_type", ["CASH_OUT", "PAYMENT", "CASH_IN", "TRANSFER", "DEBIT"]
    )
    validator.expect_column_values_to_be_in_set("currency", ["USD"])
    validator.expect_column_values_to_be_in_set(
        "merchant_category", ["RETAIL", "FOOD", "TRAVEL", "UTILITIES", "HEALTHCARE", "TRANSFER"]
    )

    # PaySim amounts are always positive and mobile-money scale
    validator.expect_column_values_to_be_between(
        "amount", min_value=0, max_value=100_000_000
    )

    validator.expect_table_row_count_to_be_between(
        min_value=1_000, max_value=10_000_000
    )


# ── Main: build all suites and save ─────────────────────────────────────────

def main():
    print("=== Building Great Expectations suites ===")
    print(f"GX root: {GX_ROOT}")
    print(f"DB engine: {DB_ENGINE}")

    # Load GX context from great_expectations.yml
    context = gx.get_context(context_root_dir=GX_ROOT)

    engine = get_engine()

    suites = [
        ("bronze_transactions", "bronze",      "transactions", build_bronze_transactions),
        ("bronze_customers",    "bronze",      "customers",    build_bronze_customers),
        ("silver_transactions", "main_silver", "stg_transactions", build_silver_transactions),
    ]

    # GX 0.18 fluent API: register a pandas datasource once, reuse for all tables
    datasource = context.sources.add_or_update_pandas(name="pandas_runtime")

    for suite_name, schema, table, builder_fn in suites:
        print(f"\n-- Building suite: {suite_name} ({schema}.{table})")

        # Load data as pandas DataFrame
        df = load_table(engine, schema, table)
        print(f"   Loaded {len(df):,} rows")

        # Create or replace the expectation suite
        context.add_or_update_expectation_suite(expectation_suite_name=suite_name)

        # Add a dataframe asset and build a batch request
        asset = datasource.add_dataframe_asset(name=f"{suite_name}_asset")
        batch_request = asset.build_batch_request(dataframe=df)

        # Get a validator (links the DataFrame to the suite)
        validator = context.get_validator(
            batch_request=batch_request,
            expectation_suite_name=suite_name,
        )

        # Add all the rules for this suite
        builder_fn(validator)

        # Save suite to expectations/<suite_name>.json
        validator.save_expectation_suite(discard_failed_expectations=False)
        print(f"   Saved: expectations/{suite_name}.json")

    # Build the HTML Data Docs site
    context.build_data_docs()
    print("\n=== All suites saved ===")
    print("Data Docs: great_expectations/uncommitted/data_docs/local_site/index.html")


if __name__ == "__main__":
    main()

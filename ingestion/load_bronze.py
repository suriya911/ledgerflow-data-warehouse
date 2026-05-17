"""
Bronze layer loader — Step 3 of the LedgerFlow medallion pipeline.

What this file does:
  1. Reads each raw CSV from data/raw/
  2. Runs schema drift detection BEFORE any row lands in the database
  3. Appends audit metadata columns (_loaded_at, _source_file, _batch_id)
  4. Writes rows into the bronze schema (PostgreSQL in prod, DuckDB locally)
  5. Optionally archives the raw CSV to AWS S3

How the DB is chosen (DB_ENGINE env var):
  - "duckdb"    -> uses a local file ledgerflow.duckdb  (no server needed)
  - "postgres"  -> connects to PostgreSQL via DATABASE_URL
  Default is duckdb so you can run this with zero infrastructure.

Why append-only?
  Bronze is an immutable log. Every pipeline run adds a new batch with its own
  _batch_id. If you need to debug "what data caused a bad number on Tuesday",
  you filter WHERE _batch_id = '20260514_060000'. You never lose history.

Audit columns added to every row:
  _loaded_at   : timestamp when this row was written to bronze
  _source_file : which CSV file it came from
  _batch_id    : a run-level timestamp shared by all tables in one run
"""

import logging
import os
import sys

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from schema_validator import detect_drift

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Which database engine to use ────────────────────────────────────────────
DB_ENGINE = os.getenv("DB_ENGINE", "duckdb").lower()

# PostgreSQL settings (used when DB_ENGINE=postgres)
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_USER     = os.getenv("DB_USER", "ledger")
DB_PASSWORD = os.getenv("DB_PASSWORD", "ledger")
DB_NAME     = os.getenv("DB_NAME", "ledgerflow")
POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# DuckDB settings (used when DB_ENGINE=duckdb)
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "ledgerflow.duckdb")

# S3 settings (optional)
USE_S3    = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "")

BRONZE_SCHEMA = "bronze"
BATCH_ID = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")


# ── Engine factory ───────────────────────────────────────────────────────────

def _make_engine():
    """
    Build a SQLAlchemy engine for either PostgreSQL or DuckDB.

    SQLAlchemy is a Python library that provides a single interface for many
    databases. You write the same df.to_sql() call and SQLAlchemy figures out
    the correct SQL dialect underneath.
    """
    if DB_ENGINE == "duckdb":
        from sqlalchemy import create_engine as _ce
        # duckdb+duckdb:///path means "file-based DuckDB database at this path"
        engine = _ce(f"duckdb:///{DUCKDB_PATH}", connect_args={"read_only": False})
        log.info("Using DuckDB -> %s", os.path.abspath(DUCKDB_PATH))
        return engine
    else:
        from sqlalchemy import create_engine as _ce
        engine = _ce(POSTGRES_URL)
        log.info("Using PostgreSQL -> %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
        return engine


def _ensure_schema(engine) -> None:
    """
    Create the bronze schema if it doesn't already exist.

    A schema in PostgreSQL/DuckDB is like a folder inside a database.
    All raw tables live under bronze.* to separate them from silver.* and gold.*
    """
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {BRONZE_SCHEMA}"))
    log.info("Schema '%s' ready.", BRONZE_SCHEMA)


# ── S3 archive (optional, production only) ──────────────────────────────────

def _upload_to_s3(filepath: str, table_name: str) -> None:
    """
    Archive the raw CSV in S3 under a date-partitioned prefix.

    S3 path pattern:  s3://ledgerflow-raw-<account>/raw/<table>/YYYY/MM/DD/<file>.csv

    Why store in S3?
      - Raw files are cheap to keep forever on S3 (~$0.02/GB/month)
      - If your database is ever corrupted or accidentally dropped,
        you can re-load from S3 instead of asking the upstream to resend
      - S3 + Glue can catalog these files for ad-hoc Athena queries too
    """
    import boto3
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
    date_prefix = pd.Timestamp.now().strftime("%Y/%m/%d")
    key = f"raw/{table_name}/{date_prefix}/{os.path.basename(filepath)}"
    s3.upload_file(filepath, S3_BUCKET, key)
    log.info("S3 upload complete: s3://%s/%s", S3_BUCKET, key)


# ── Core load function ───────────────────────────────────────────────────────

def load_to_bronze(filepath: str, table_name: str, engine) -> int:
    """
    Load one CSV into bronze.<table_name>.

    Steps:
      1. Read CSV into a pandas DataFrame
      2. Detect schema drift (abort if critical)
      3. Add audit columns
      4. Write to database (append)
      5. Optionally upload to S3

    Returns the number of rows loaded.
    Raises ValueError if critical schema drift is detected.
    """
    log.info("--- Loading %s ---", table_name.upper())
    log.info("Reading: %s", filepath)

    df = pd.read_csv(filepath)
    log.info("  Shape: %d rows x %d columns", *df.shape)

    # STEP 2 — Schema drift gate
    # This is the most important safety check in the bronze layer.
    # If an upstream team dropped a column we depend on, we stop here
    # rather than loading broken data silently.
    drift = detect_drift(df, table_name)
    if drift["critical_drift"]:
        raise ValueError(
            f"HALTED: Critical schema drift in '{table_name}'. "
            f"Missing columns: {drift['missing_columns']}. "
            "Fix the upstream source and re-run."
        )

    # STEP 3 — Audit metadata
    # These three columns are not in the source data.
    # We inject them here so we always know the provenance of every row.
    df["_loaded_at"]   = pd.Timestamp.now().isoformat()
    df["_source_file"] = os.path.basename(filepath)
    df["_batch_id"]    = BATCH_ID

    # STEP 4 — Write to database
    # if_exists="append"  -> add rows to existing table (never delete)
    # method="multi"      -> one INSERT per chunk (much faster than one INSERT per row)
    # chunksize=5000      -> send 5000 rows per INSERT statement
    df.to_sql(
        name=table_name,
        con=engine,
        schema=BRONZE_SCHEMA,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=5_000,
    )
    log.info("  Written: %d rows -> %s.%s (batch %s)", len(df), BRONZE_SCHEMA, table_name, BATCH_ID)

    # STEP 5 — S3 archive (only when explicitly enabled)
    if USE_S3 and S3_BUCKET:
        _upload_to_s3(filepath, table_name)

    return len(df)


# ── Orchestrate all four tables ──────────────────────────────────────────────

def load_all_bronze() -> None:
    """
    Load all four source tables into bronze in sequence.

    Order matters slightly: customers before transactions because downstream
    foreign key checks in silver expect customers to exist.
    But in bronze we load all as-is — no FK enforcement here.
    """
    engine = _make_engine()
    _ensure_schema(engine)

    sources = [
        ("data/raw/customers.csv",    "customers"),
        ("data/raw/accounts.csv",     "accounts"),
        ("data/raw/loans.csv",        "loans"),
        ("data/raw/transactions.csv", "transactions"),
    ]

    total_rows = 0
    loaded_tables = []

    for filepath, table_name in sources:
        if not os.path.exists(filepath):
            log.warning("File not found: %s -- run the data generator first.", filepath)
            continue
        rows = load_to_bronze(filepath, table_name, engine)
        total_rows += rows
        loaded_tables.append(table_name)

    log.info("")
    log.info("=== Bronze load complete ===")
    log.info("Tables loaded : %s", ", ".join(loaded_tables))
    log.info("Total rows    : %d", total_rows)
    log.info("Batch ID      : %s", BATCH_ID)
    log.info("Engine        : %s", DB_ENGINE)


if __name__ == "__main__":
    load_all_bronze()

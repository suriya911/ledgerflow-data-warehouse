"""
load_fusion_bronze.py — Land BOTH source systems into the bronze schema.

LedgerFlow's "fusion" warehouse integrates two heterogeneous payment platforms:

  CARD channel        -> IBM credit-card dataset (computingvictor/transactions-fraud-datasets)
                         transactions_data.csv (~13.3M), users_data.csv, cards_data.csv,
                         mcc_codes.json, train_fraud_labels.json
  MOBILE_MONEY channel-> PaySim mobile-money dataset (ealaxi/paysim1, ~6.36M)

This loader reads the raw files AS-IS into bronze.* (the medallion "land raw"
rule), adding audit columns. All cleaning/typing happens later in dbt staging.

Why DuckDB native reads:
  transactions_data.csv is 1.26 GB / 13.3M rows. DuckDB's read_csv ingests it in
  seconds — no pandas chunking. The JSON sidecars (mcc, fraud labels) are small
  enough to load via Python and register as relations.

Real-world quirks handled here (good interview material):
  - IBM `amount` is a string like "$-77.00"  -> kept as VARCHAR in bronze, parsed in silver
  - IBM `errors` has quoted commas ("Insufficient Balance,Technical Glitch") -> quote='"'
  - some IBM rows break strict CSV  -> strict_mode=false
  - fraud labels live in a separate JSON {"target": {txn_id: "Yes"/"No"}}
"""

import json
import logging
import os

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUCKDB_PATH = os.getenv("DUCKDB_PATH", os.path.join(REPO_ROOT, "ledgerflow.duckdb"))

IBM_DIR = os.path.join(REPO_ROOT, "data", "raw", "ibm")
PAYSIM_DIR = os.path.join(REPO_ROOT, "data", "raw", "paysim")

BRONZE = "bronze"
BATCH_ID = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")


def _audit_cols(source_file: str) -> str:
    """SQL fragment adding the three standard bronze audit columns."""
    return (
        f"current_timestamp as _loaded_at, "
        f"'{source_file}' as _source_file, "
        f"'{BATCH_ID}' as _batch_id"
    )


def _paysim_csv() -> str:
    files = [f for f in os.listdir(PAYSIM_DIR) if f.lower().endswith(".csv")]
    if not files:
        raise FileNotFoundError(f"No PaySim CSV in {PAYSIM_DIR}")
    return os.path.join(PAYSIM_DIR, files[0])


def load(con: duckdb.DuckDBPyConnection):
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {BRONZE}")

    # ── IBM card transactions (13.3M) ────────────────────────────────────────
    txns_csv = os.path.join(IBM_DIR, "transactions_data.csv").replace("\\", "/")
    log.info("Loading IBM transactions (this is the big one) ...")
    con.execute(f"""
        CREATE OR REPLACE TABLE {BRONZE}.ibm_transactions AS
        SELECT *, {_audit_cols('transactions_data.csv')}
        FROM read_csv_auto('{txns_csv}', quote='"', strict_mode=false,
                           sample_size=-1, null_padding=true)
    """)
    n_ibm = con.execute(f"SELECT count(*) FROM {BRONZE}.ibm_transactions").fetchone()[0]
    log.info("  bronze.ibm_transactions: %s rows", f"{n_ibm:,}")

    # ── IBM users (customer master) + cards ──────────────────────────────────
    users_csv = os.path.join(IBM_DIR, "users_data.csv").replace("\\", "/")
    cards_csv = os.path.join(IBM_DIR, "cards_data.csv").replace("\\", "/")
    con.execute(f"""
        CREATE OR REPLACE TABLE {BRONZE}.ibm_users AS
        SELECT *, {_audit_cols('users_data.csv')}
        FROM read_csv_auto('{users_csv}', sample_size=-1)
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE {BRONZE}.ibm_cards AS
        SELECT *, {_audit_cols('cards_data.csv')}
        FROM read_csv_auto('{cards_csv}', sample_size=-1)
    """)
    log.info("  bronze.ibm_users: %s rows",
             f"{con.execute(f'SELECT count(*) FROM {BRONZE}.ibm_users').fetchone()[0]:,}")
    log.info("  bronze.ibm_cards: %s rows",
             f"{con.execute(f'SELECT count(*) FROM {BRONZE}.ibm_cards').fetchone()[0]:,}")

    # ── MCC code -> category lookup (small JSON object) ──────────────────────
    with open(os.path.join(IBM_DIR, "mcc_codes.json")) as f:
        mcc = json.load(f)
    mcc_df = pd.DataFrame(
        [{"mcc": int(k), "mcc_category": v} for k, v in mcc.items()]
    )
    con.register("_mcc_df", mcc_df)
    con.execute(f"CREATE OR REPLACE TABLE {BRONZE}.ibm_mcc AS SELECT * FROM _mcc_df")
    con.unregister("_mcc_df")
    log.info("  bronze.ibm_mcc: %s rows", f"{len(mcc_df):,}")

    # ── Fraud labels (separate JSON: {"target": {txn_id: "Yes"/"No"}}) ───────
    log.info("Loading IBM fraud labels (159 MB JSON) ...")
    with open(os.path.join(IBM_DIR, "train_fraud_labels.json")) as f:
        labels = json.load(f)["target"]
    labels_df = pd.DataFrame(
        {"transaction_id": list(labels.keys()), "fraud_label": list(labels.values())}
    )
    labels_df["transaction_id"] = pd.to_numeric(labels_df["transaction_id"])
    con.register("_labels_df", labels_df)
    con.execute(f"CREATE OR REPLACE TABLE {BRONZE}.ibm_fraud_labels AS SELECT * FROM _labels_df")
    con.unregister("_labels_df")
    log.info("  bronze.ibm_fraud_labels: %s rows", f"{len(labels_df):,}")

    # ── PaySim mobile-money transactions (6.36M) ─────────────────────────────
    ps_csv = _paysim_csv().replace("\\", "/")
    log.info("Loading PaySim transactions ...")
    con.execute(f"""
        CREATE OR REPLACE TABLE {BRONZE}.paysim_transactions AS
        SELECT *, {_audit_cols(os.path.basename(ps_csv))}
        FROM read_csv_auto('{ps_csv}', sample_size=-1)
    """)
    n_ps = con.execute(f"SELECT count(*) FROM {BRONZE}.paysim_transactions").fetchone()[0]
    log.info("  bronze.paysim_transactions: %s rows", f"{n_ps:,}")

    log.info("")
    log.info("=== Fusion bronze load complete ===")
    log.info("CARD (IBM)         : %s txns", f"{n_ibm:,}")
    log.info("MOBILE_MONEY (PS)  : %s txns", f"{n_ps:,}")
    log.info("UNIFIED TOTAL      : %s txns", f"{n_ibm + n_ps:,}")
    log.info("Batch ID           : %s", BATCH_ID)


if __name__ == "__main__":
    log.info("DuckDB -> %s", DUCKDB_PATH)
    con = duckdb.connect(DUCKDB_PATH)
    try:
        load(con)
    finally:
        con.close()

"""
Schema drift detector for bronze ingestion.

How it works:
  - EXPECTED_SCHEMAS defines the columns and dtypes we expect from each source.
  - detect_drift() compares the incoming DataFrame's columns against that spec.
  - Missing columns = critical drift  -> pipeline must stop (data is broken).
  - New columns    = non-critical     -> log a warning, still load (upstream added a field).
  - Type mismatches                   -> logged as warnings; load proceeds because
                                         Postgres will catch hard mismatches anyway.

Why this matters:
  Upstream teams rename or drop columns without telling you. Without this check,
  your dbt models silently return NULLs and dashboards show wrong numbers for days.
"""

import logging

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Canonical column -> expected pandas dtype string
EXPECTED_SCHEMAS: dict[str, dict[str, str]] = {
    "transactions": {
        # PaySim-mapped schema (see data_generator/load_paysim.py for column derivation)
        "transaction_id":    "object",
        "account_id":        "object",
        "customer_id":       "object",
        "transaction_type":  "object",
        "amount":            "float64",
        "currency":          "object",
        "merchant_category": "object",
        "orig_account_id":   "object",   # PaySim nameOrig — preserved for lineage
        "dest_account_id":   "object",   # PaySim nameDest
        "balance_before":    "float64",
        "balance_after":     "float64",
        "dest_balance_before": "float64",
        "dest_balance_after":  "float64",
        "is_fraud":          "int64",
        "is_flagged_fraud":  "int64",
        "transaction_date":  "object",
        "created_at":        "object",
    },
    "customers": {
        "customer_id": "object",
        "full_name": "object",
        "email": "object",
        "phone": "object",
        "address": "object",
        "segment": "object",
        "kyc_status": "object",
        "created_at": "object",
        "updated_at": "object",
    },
    "accounts": {
        "account_id": "object",
        "customer_id": "object",
        "account_type": "object",
        "balance": "float64",
        "opened_date": "object",
        "status": "object",
        "product_id": "object",
    },
    "loans": {
        "loan_id": "object",
        "customer_id": "object",
        "account_id": "object",
        "principal": "float64",
        "interest_rate": "float64",
        "term_months": "int64",
        "disbursement_date": "object",
        "maturity_date": "object",
        "status": "object",
    },
}


def detect_drift(df: pd.DataFrame, table_name: str) -> dict:
    """
    Compare df columns against the expected schema for table_name.

    Returns a dict:
      {
        "missing_columns": [...],   # columns we expected but didn't find
        "new_columns":     [...],   # columns we didn't expect but found
        "type_mismatches": [...],   # (col, expected_dtype, actual_dtype) tuples
        "critical_drift":  bool,    # True if missing_columns is non-empty
      }
    """
    expected = EXPECTED_SCHEMAS.get(table_name)
    if expected is None:
        log.warning("No schema registered for table '%s' — skipping drift check.", table_name)
        return {"missing_columns": [], "new_columns": [], "type_mismatches": [], "critical_drift": False}

    expected_cols = set(expected.keys())
    actual_cols = set(df.columns)

    missing = sorted(expected_cols - actual_cols)
    new_cols = sorted(actual_cols - expected_cols)

    type_mismatches = []
    for col, expected_dtype in expected.items():
        if col in df.columns:
            actual_dtype = str(df[col].dtype)
            if actual_dtype != expected_dtype:
                type_mismatches.append((col, expected_dtype, actual_dtype))

    if missing:
        log.error(
            "CRITICAL DRIFT in '%s': missing columns %s", table_name, missing
        )
    if new_cols:
        log.warning(
            "NEW COLUMNS in '%s' (non-critical): %s", table_name, new_cols
        )
    if type_mismatches:
        for col, exp, act in type_mismatches:
            log.warning(
                "TYPE MISMATCH in '%s'.%s: expected %s, got %s", table_name, col, exp, act
            )

    return {
        "missing_columns": missing,
        "new_columns": new_cols,
        "type_mismatches": type_mismatches,
        "critical_drift": len(missing) > 0,
    }

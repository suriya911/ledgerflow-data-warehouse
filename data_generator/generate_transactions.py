"""
Generate synthetic PaySim-compatible banking transactions (vectorized, scalable).

Why this schema:
  The entire downstream stack — schema_validator.py, the GX bronze_transactions
  suite, stg_transactions.sql, fact_transactions.sql and fact_fraud_alerts.sql —
  is built around the PaySim schema (see data_generator/load_paysim.py). The real
  PaySim source is a 470 MB Kaggle download. This generator produces the SAME 17
  columns with PaySim-like distributions so the full medallion pipeline runs
  end-to-end locally without that download — and it scales to millions of rows.

Vectorized:
  All columns are built with numpy/pandas array operations (no Python row loop),
  so 1,000,000 rows generate in a few seconds instead of minutes.

CLI:
  python generate_transactions.py [N] [START_DATE] [DAYS] [OUT_PATH]
    N          number of rows           (default 50000)
    START_DATE first day, ISO yyyy-mm-dd (default 2024-01-01)
    DAYS       span of days for the batch(default 31)
    OUT_PATH   output csv                (default data/raw/transactions.csv)

  The START_DATE / DAYS window lets the benchmark create DISTINCT daily batches:
  a base batch in Jan and a later "today" delta batch — so the incremental
  watermark (created_at) cleanly separates new rows from old.

Columns produced (identical to load_paysim.py output):
  transaction_id, account_id, customer_id, transaction_type, amount, currency,
  merchant_category, orig_account_id, dest_account_id, balance_before,
  balance_after, dest_balance_before, dest_balance_after, is_fraud,
  is_flagged_fraud, transaction_date, created_at
"""

import os
import sys
import uuid
from datetime import datetime

import numpy as np
import pandas as pd

SEED = 42

TRANSACTION_TYPES = np.array(["CASH_OUT", "PAYMENT", "CASH_IN", "TRANSFER", "DEBIT"])
TYPE_WEIGHTS = np.array([0.35, 0.34, 0.22, 0.08, 0.01])  # PaySim-like mix
MERCHANT_CATEGORIES = np.array(["RETAIL", "FOOD", "TRAVEL", "UTILITIES", "HEALTHCARE"])

# ID pools — must match generate_customers / generate_accounts output
ACCOUNT_IDS = np.array([f"ACC{i:04d}" for i in range(1000, 4001)])    # 3 000 accounts
CUSTOMER_IDS = np.array([f"CUST{i:03d}" for i in range(100, 1100)])   # 1 000 customers


def generate_transactions(
    n: int = 50_000,
    start_date: str = "2024-01-01",
    days: int = 31,
    seed: int = SEED,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # transaction_type, then derive merchant vs customer destinations
    ttype = rng.choice(TRANSACTION_TYPES, size=n, p=TYPE_WEIGHTS)
    dest_is_merchant = np.isin(ttype, ["PAYMENT", "DEBIT"])

    # PaySim-style external account ids: C######### / M#########
    def paysim_ids(prefix_is_merchant: np.ndarray) -> np.ndarray:
        digits = rng.integers(100_000_000, 1_000_000_000, size=n).astype("U9")
        prefixes = np.where(prefix_is_merchant, "M", "C")
        return np.char.add(prefixes, digits)

    orig_account_id = paysim_ids(np.zeros(n, dtype=bool))         # always customer
    dest_account_id = paysim_ids(dest_is_merchant)

    # merchant_category: real category when dest is a merchant, else TRANSFER
    merchant_cat = np.where(
        dest_is_merchant,
        rng.choice(MERCHANT_CATEGORIES, size=n),
        "TRANSFER",
    )

    # amount: lognormal tuned so mean lands in GX's 50k–500k band; always > 0
    amount = np.round(rng.lognormal(mean=11.5, sigma=1.1, size=n), 2)
    amount = np.clip(amount, 1.0, 92_000_000.0)

    # balances
    balance_before = np.round(rng.uniform(0, 5_000_000, size=n), 2)
    balance_after = np.clip(np.round(balance_before - amount, 2), 0, None)
    dest_balance_before = np.round(rng.uniform(0, 5_000_000, size=n), 2)
    dest_balance_after = np.round(dest_balance_before + amount, 2)

    # fraud: rare (~PaySim scale), concentrated in CASH_OUT / TRANSFER
    fraud_eligible = np.isin(ttype, ["CASH_OUT", "TRANSFER"])
    is_fraud = (fraud_eligible & (rng.random(n) < 0.004)).astype(int)
    # rules engine flags only ~40% of true fraud, nothing else
    is_flagged_fraud = ((is_fraud == 1) & (rng.random(n) < 0.4)).astype(int)

    # timestamps spread across [start_date, start_date + days)
    start = np.datetime64(datetime.fromisoformat(start_date))
    offsets = rng.integers(0, max(days, 1) * 24 * 3600, size=n).astype("timedelta64[s]")
    created = start + offsets
    created_at = pd.to_datetime(created)

    # transaction_id: 1M uuids in a list comp is ~1–2s (uuid has no vector form)
    transaction_id = [str(uuid.uuid4()) for _ in range(n)]

    return pd.DataFrame(
        {
            "transaction_id": transaction_id,
            "account_id": rng.choice(ACCOUNT_IDS, size=n),
            "customer_id": rng.choice(CUSTOMER_IDS, size=n),
            "transaction_type": ttype,
            "amount": amount,
            "currency": "USD",
            "merchant_category": merchant_cat,
            "orig_account_id": orig_account_id,
            "dest_account_id": dest_account_id,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "dest_balance_before": dest_balance_before,
            "dest_balance_after": dest_balance_after,
            "is_fraud": is_fraud,
            "is_flagged_fraud": is_flagged_fraud,
            "transaction_date": created_at.normalize().strftime("%Y-%m-%d"),
            "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000
    start_date = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 31
    out = sys.argv[4] if len(sys.argv) > 4 else "data/raw/transactions.csv"

    os.makedirs(os.path.dirname(out), exist_ok=True)
    df = generate_transactions(n, start_date, days)
    df.to_csv(out, index=False)

    fraud_count = int(df["is_fraud"].sum())
    print(f"Generated {len(df):,} transactions -> {out}")
    print(f"Date window: {df['transaction_date'].min()} .. {df['transaction_date'].max()}")
    print(f"Amount mean: ${df['amount'].mean():,.0f} (GX expects 50k-500k)")
    print(f"Fraud: {fraud_count} ({fraud_count/len(df)*100:.3f}%)")

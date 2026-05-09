"""
load_paysim.py — Map PaySim columns to LedgerFlow's transaction schema.

What PaySim is:
  PaySim is a financial fraud simulator based on real mobile money data
  from a month of financial logs from a mobile money service in Africa.
  It has 6.36 million rows and 8,213 confirmed fraud transactions.
  Source: https://www.kaggle.com/datasets/ealaxi/paysim1
  License: CC BY-SA 4.0

What this script does:
  1. Reads the raw PaySim CSV (470 MB)
  2. Maps PaySim column names to LedgerFlow's bronze schema
  3. Derives real timestamps from the 'step' field (step=1 hour, base=2024-01-01)
  4. Links transactions to our Faker-generated customer/account IDs
     so joins work across the medallion layers
  5. Writes data/raw/transactions.csv for load_bronze.py to ingest

Column mapping:
  PaySim          -> LedgerFlow
  step            -> transaction_hour (int) + transaction_date + created_at (derived)
  type            -> transaction_type
  amount          -> amount
  nameOrig        -> orig_account_id (original PaySim ID, preserved for lineage)
  nameDest        -> dest_account_id
  oldbalanceOrg   -> balance_before
  newbalanceOrig  -> balance_after
  oldbalanceDest  -> dest_balance_before
  newbalanceDest  -> dest_balance_after
  isFraud         -> is_fraud
  isFlaggedFraud  -> is_flagged_fraud

  account_id      -> randomly assigned from our Faker account pool (for dim joins)
  customer_id     -> randomly assigned from our Faker customer pool
  transaction_id  -> generated UUID (PaySim has no natural transaction ID)
  currency        -> USD (PaySim is single-currency)
  merchant_category -> derived from nameDest prefix (M=MERCHANT, C=CUSTOMER)

Why we assign Faker account/customer IDs:
  PaySim's nameOrig (e.g. C1231006815) doesn't match our dim_customer.
  We randomly link each transaction to one of our 1,000 Faker customers
  so the star schema joins work end-to-end. In a real project, you'd
  have a proper entity resolution step here.
"""

import os
import random
import uuid
from datetime import datetime, timedelta

import pandas as pd

random.seed(42)

PAYSIM_FILE = "data/raw/PS_20174392719_1491204439457_log.csv"
OUT_FILE    = "data/raw/transactions.csv"

# Our Faker-generated ID pools (must match generate_customers/accounts output)
CUSTOMER_IDS = [f"CUST{i:03d}" for i in range(100, 1100)]   # 1 000 customers
ACCOUNT_IDS  = [f"ACC{i:04d}" for i in range(1000, 4001)]   # 3 000 accounts

# PaySim simulation base date: treat step=1 as 2024-01-01 00:00
BASE_DATE = datetime(2024, 1, 1)

# Map PaySim type names to our standard (PaySim uses underscores)
TYPE_MAP = {
    "CASH_OUT": "CASH_OUT",
    "PAYMENT":  "PAYMENT",
    "CASH_IN":  "CASH_IN",
    "TRANSFER": "TRANSFER",
    "DEBIT":    "DEBIT",
}


def step_to_timestamp(step: int) -> datetime:
    """Convert PaySim step (1 hour increments) to a real datetime."""
    return BASE_DATE + timedelta(hours=int(step))


def merchant_category(name_dest: str) -> str:
    """
    Derive a merchant category from the destination account prefix.
    PaySim prefixes: C = customer-to-customer, M = customer-to-merchant
    """
    if str(name_dest).startswith("M"):
        return random.choice(["RETAIL", "FOOD", "UTILITIES", "HEALTHCARE", "TRAVEL"])
    return "TRANSFER"   # C-to-C is an internal transfer


def load_paysim(sample_size: int = None) -> pd.DataFrame:
    """
    Load and transform PaySim data.

    Args:
        sample_size: if set, take a random sample of this many rows.
                     None = use all 6.36M rows.
                     Recommended: None for full run, 500_000 for quick test.
    """
    print(f"Reading {PAYSIM_FILE} ...")
    df = pd.read_csv(PAYSIM_FILE)
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")

    if sample_size:
        df = df.sample(n=sample_size, random_state=42).reset_index(drop=True)
        print(f"  Sampled to {len(df):,} rows")

    print("Transforming columns ...")

    # Derive timestamps from step field
    timestamps = [step_to_timestamp(s) for s in df["step"]]
    df["created_at"]       = [t.isoformat() for t in timestamps]
    df["transaction_date"] = [t.date().isoformat() for t in timestamps]

    # Generate UUIDs for transaction_id (PaySim has no natural key)
    df["transaction_id"] = [str(uuid.uuid4()) for _ in range(len(df))]

    # Randomly assign to our Faker customer/account pools
    df["account_id"]  = [random.choice(ACCOUNT_IDS)  for _ in range(len(df))]
    df["customer_id"] = [random.choice(CUSTOMER_IDS) for _ in range(len(df))]

    # Merchant category from destination account prefix
    df["merchant_category"] = df["nameDest"].apply(merchant_category)

    # Static fields
    df["currency"] = "USD"

    # Rename PaySim columns to LedgerFlow names
    df = df.rename(columns={
        "type":          "transaction_type",
        "nameOrig":      "orig_account_id",
        "nameDest":      "dest_account_id",
        "oldbalanceOrg": "balance_before",
        "newbalanceOrig":"balance_after",
        "oldbalanceDest":"dest_balance_before",
        "newbalanceDest":"dest_balance_after",
        "isFraud":       "is_fraud",
        "isFlaggedFraud":"is_flagged_fraud",
    })

    # Select and order final columns
    output_cols = [
        "transaction_id",
        "account_id",
        "customer_id",
        "transaction_type",
        "amount",
        "currency",
        "merchant_category",
        "orig_account_id",
        "dest_account_id",
        "balance_before",
        "balance_after",
        "dest_balance_before",
        "dest_balance_after",
        "is_fraud",
        "is_flagged_fraud",
        "transaction_date",
        "created_at",
    ]

    return df[output_cols]


if __name__ == "__main__":
    import sys
    os.makedirs("data/raw", exist_ok=True)

    # Accept optional sample size from CLI: python load_paysim.py 500000
    sample = int(sys.argv[1]) if len(sys.argv) > 1 else None

    df = load_paysim(sample_size=sample)

    df.to_csv(OUT_FILE, index=False)

    fraud_count = df["is_fraud"].sum()
    fraud_pct   = fraud_count / len(df) * 100
    types       = df["transaction_type"].value_counts().to_dict()

    print(f"\nWrote {len(df):,} rows -> {OUT_FILE}")
    print(f"Fraud transactions: {fraud_count:,} ({fraud_pct:.3f}%)")
    print(f"Transaction types: {types}")
    print(f"Date range: {df['transaction_date'].min()} to {df['transaction_date'].max()}")

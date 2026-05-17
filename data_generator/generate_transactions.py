"""
Generate synthetic banking transactions.
Intentionally injects ~3% null transaction_date values so Great Expectations
can catch them and validate the 95% non-null threshold.
"""

import os
import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

TRANSACTION_TYPES = ["DEBIT", "CREDIT", "TRANSFER", "WITHDRAWAL"]
CURRENCIES = ["USD", "EUR", "GBP"]
MERCHANT_CATEGORIES = ["RETAIL", "FOOD", "TRAVEL", "UTILITIES", "HEALTHCARE"]
STATUSES = ["COMPLETED", "PENDING", "FAILED", "REVERSED"]

# Keep account and customer ID pools consistent with other generators
ACCOUNT_IDS = [f"ACC{i:04d}" for i in range(1000, 4001)]   # 3 000 accounts
CUSTOMER_IDS = [f"CUST{i:03d}" for i in range(100, 1100)]  # 1 000 customers


def generate_transactions(n: int = 50_000) -> pd.DataFrame:
    records = []
    for _ in range(n):
        null_date = random.random() < 0.03  # 3% injected nulls
        records.append(
            {
                "transaction_id": fake.uuid4(),
                "account_id": random.choice(ACCOUNT_IDS),
                "customer_id": random.choice(CUSTOMER_IDS),
                "transaction_type": random.choice(TRANSACTION_TYPES),
                "amount": round(random.uniform(-5_000, 10_000), 2),
                "currency": random.choice(CURRENCIES),
                "merchant_category": random.choice(MERCHANT_CATEGORIES),
                "status": random.choice(STATUSES),
                "transaction_date": None if null_date else fake.date_this_year().isoformat(),
                "created_at": fake.date_time_between(
                    start_date="-2y", end_date="now"
                ).isoformat(),
            }
        )
    return pd.DataFrame(records)


if __name__ == "__main__":
    os.makedirs("data/raw", exist_ok=True)
    df = generate_transactions(50_000)
    out = "data/raw/transactions.csv"
    df.to_csv(out, index=False)
    null_count = df["transaction_date"].isna().sum()
    null_pct = null_count / len(df) * 100
    print(f"Generated {len(df):,} transactions -> {out}")
    print(f"Null transaction_date: {null_count} ({null_pct:.1f}%) -- GX 95% threshold test")

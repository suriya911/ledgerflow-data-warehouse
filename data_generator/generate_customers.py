"""
Generate synthetic banking customers.
Produces 1 000 customers with segments, KYC status, and multiple historical
rows per customer (simulating updates) to exercise the SCD Type 2 dim_customer.
"""

import os
import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

SEGMENTS = ["RETAIL", "PREMIUM", "CORPORATE"]
KYC_STATUSES = ["VERIFIED", "PENDING", "FAILED", "EXPIRED"]

SEGMENT_WEIGHTS = [0.65, 0.25, 0.10]  # RETAIL majority


def _random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def generate_customers(n: int = 1_000) -> pd.DataFrame:
    records = []
    now = datetime.now()
    start = datetime(2020, 1, 1)

    for i in range(n):
        customer_id = f"CUST{i + 100:03d}"
        created_at = _random_date(start, now - timedelta(days=30))

        # Base record
        segment = random.choices(SEGMENTS, weights=SEGMENT_WEIGHTS, k=1)[0]
        records.append(
            {
                "customer_id": customer_id,
                "full_name": fake.name(),
                "email": fake.unique.email(),
                "phone": fake.phone_number(),
                "address": fake.address().replace("\n", ", "),
                "segment": segment,
                "kyc_status": random.choice(KYC_STATUSES),
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
            }
        )

        # ~30% of customers have a second row (segment/kyc change) — drives SCD2
        if random.random() < 0.30:
            updated_at = _random_date(created_at + timedelta(days=1), now)
            new_segment = random.choice([s for s in SEGMENTS if s != segment])
            records.append(
                {
                    "customer_id": customer_id,
                    "full_name": records[-1]["full_name"],
                    "email": records[-1]["email"],
                    "phone": fake.phone_number(),
                    "address": fake.address().replace("\n", ", "),
                    "segment": new_segment,
                    "kyc_status": random.choice(KYC_STATUSES),
                    "created_at": created_at.isoformat(),
                    "updated_at": updated_at.isoformat(),
                }
            )

    return pd.DataFrame(records)


if __name__ == "__main__":
    os.makedirs("data/raw", exist_ok=True)
    df = generate_customers(1_000)
    out = "data/raw/customers.csv"
    df.to_csv(out, index=False)
    unique_customers = df["customer_id"].nunique()
    multi_row = df[df.duplicated("customer_id", keep=False)]["customer_id"].nunique()
    print(f"Generated {len(df):,} customer rows ({unique_customers} unique) -> {out}")
    print(f"Customers with multiple versions (SCD2 candidates): {multi_row}")

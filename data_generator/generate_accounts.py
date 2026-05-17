"""
Generate synthetic bank accounts.
3 000 accounts linked to the 1 000 customers (avg 3 accounts per customer).
product_id links to dim_product in the gold layer.
"""

import os
import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

ACCOUNT_TYPES = ["CHECKING", "SAVINGS", "LOAN"]
STATUSES = ["ACTIVE", "INACTIVE", "CLOSED", "FROZEN"]
PRODUCT_IDS = [f"PROD{i:03d}" for i in range(1, 21)]  # 20 products

CUSTOMER_IDS = [f"CUST{i:03d}" for i in range(100, 1100)]


def _random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def generate_accounts(n: int = 3_000) -> pd.DataFrame:
    records = []
    now = datetime.now()
    start = datetime(2018, 1, 1)

    for i in range(n):
        opened = _random_date(start, now - timedelta(days=7))
        account_type = random.choice(ACCOUNT_TYPES)

        if account_type == "CHECKING":
            balance = round(random.uniform(0, 50_000), 2)
        elif account_type == "SAVINGS":
            balance = round(random.uniform(1_000, 200_000), 2)
        else:
            balance = round(random.uniform(-100_000, 0), 2)  # loan = negative balance

        records.append(
            {
                "account_id": f"ACC{i + 1000:04d}",
                "customer_id": random.choice(CUSTOMER_IDS),
                "account_type": account_type,
                "balance": balance,
                "opened_date": opened.date().isoformat(),
                "status": random.choices(
                    STATUSES, weights=[0.75, 0.10, 0.10, 0.05], k=1
                )[0],
                "product_id": random.choice(PRODUCT_IDS),
            }
        )

    return pd.DataFrame(records)


if __name__ == "__main__":
    os.makedirs("data/raw", exist_ok=True)
    df = generate_accounts(3_000)
    out = "data/raw/accounts.csv"
    df.to_csv(out, index=False)
    print(f"Generated {len(df):,} accounts -> {out}")
    print(df["account_type"].value_counts().to_string())
    print(f"Status breakdown:\n{df['status'].value_counts().to_string()}")

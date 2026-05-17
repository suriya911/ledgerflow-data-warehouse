"""
Generate synthetic loan records.
500 loans linked to customers and their LOAN-type accounts.
"""

import os
import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

LOAN_STATUSES = ["ACTIVE", "CLOSED", "DEFAULTED", "RESTRUCTURED"]
TERM_OPTIONS = [12, 24, 36, 48, 60, 84, 120]  # months

CUSTOMER_IDS = [f"CUST{i:03d}" for i in range(100, 1100)]
ACCOUNT_IDS = [f"ACC{i:04d}" for i in range(1000, 4001)]


def _random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def generate_loans(n: int = 500) -> pd.DataFrame:
    records = []
    now = datetime.now()
    start = datetime(2019, 1, 1)

    for i in range(n):
        disbursed = _random_date(start, now - timedelta(days=30))
        term = random.choice(TERM_OPTIONS)
        principal = round(random.uniform(5_000, 500_000), 2)
        interest_rate = round(random.uniform(3.5, 18.0), 2)
        maturity = disbursed + timedelta(days=term * 30)
        status = (
            "CLOSED"
            if maturity < now
            else random.choices(
                LOAN_STATUSES, weights=[0.75, 0.10, 0.10, 0.05], k=1
            )[0]
        )

        records.append(
            {
                "loan_id": f"LOAN{i + 1:05d}",
                "customer_id": random.choice(CUSTOMER_IDS),
                "account_id": random.choice(ACCOUNT_IDS),
                "principal": principal,
                "interest_rate": interest_rate,
                "term_months": term,
                "disbursement_date": disbursed.date().isoformat(),
                "maturity_date": maturity.date().isoformat(),
                "status": status,
            }
        )

    return pd.DataFrame(records)


if __name__ == "__main__":
    os.makedirs("data/raw", exist_ok=True)
    df = generate_loans(500)
    out = "data/raw/loans.csv"
    df.to_csv(out, index=False)
    print(f"Generated {len(df):,} loans -> {out}")
    print(f"Status breakdown:\n{df['status'].value_counts().to_string()}")
    print(f"Principal range: ${df['principal'].min():,.2f} to ${df['principal'].max():,.2f}")

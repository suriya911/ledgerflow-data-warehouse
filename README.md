# LedgerFlow — Enterprise Banking Data Warehouse & Governance Platform

A production-grade medallion data warehouse simulating a retail banking platform.
Ingests transactions, accounts, customers, and loan records into a Bronze → Silver → Gold
pipeline with data quality gates, Airflow orchestration, AWS deployment, and a live
Vercel analytics dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Data Sources                             │
│   Transactions · Customers · Accounts · Loans (Faker/Python)    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  BRONZE LAYER (Raw Ingestion)                   │
│   schema_validator.py → load_bronze.py → PostgreSQL/RDS         │
│   + S3 raw file archive                                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │  Great Expectations bronze checkpoint
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  SILVER LAYER (dbt Staging)                     │
│   stg_transactions · stg_customers · stg_accounts · stg_loans  │
│   Cast · Trim · Null-guard · Rename                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │  Great Expectations silver checkpoint
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   GOLD LAYER (dbt Marts)                        │
│   fact_transactions · dim_customer (SCD2) · dim_account         │
│   dim_product · int_customer_accounts                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Vercel Dashboard                             │
│   Next.js 14 · KPI cards · Transaction charts · Quality badges  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer             | Tool                                     |
|-------------------|------------------------------------------|
| Warehouse (local) | PostgreSQL 15 (Docker)                   |
| Warehouse (prod)  | AWS RDS PostgreSQL 15                    |
| Raw file storage  | AWS S3                                   |
| Transformation    | dbt Core 1.8                             |
| Orchestration     | Apache Airflow 2.9 (Docker / ECS Fargate)|
| Data Quality      | Great Expectations 0.18                  |
| CI/CD             | GitHub Actions                           |
| Frontend          | Next.js 14 on Vercel                     |
| Secrets           | AWS Secrets Manager                      |

---

## Quick Start (Local)

```bash
# 1. Clone and set up env
git clone https://github.com/suriya911/ledgerflow-data-warehouse
cd ledgerflow-data-warehouse
cp .env.example .env        # fill in DB_PASSWORD etc.

# 2. Start Postgres + Airflow
docker-compose up -d

# 3. Install Python deps
pip install -r requirements.txt

# 4. Generate synthetic data
python data_generator/generate_transactions.py
python data_generator/generate_customers.py
python data_generator/generate_accounts.py
python data_generator/generate_loans.py

# 5. Load bronze layer
python ingestion/load_bronze.py

# 6. Run dbt
cd dbt_ledgerflow
dbt deps && dbt run && dbt test

# 7. View dbt docs
dbt docs generate && dbt docs serve

# 8. Run Great Expectations
great_expectations checkpoint run bronze_checkpoint
great_expectations checkpoint run silver_checkpoint
```

Airflow UI: http://localhost:8080 (admin / admin)

---

## AWS Deployment

See [`aws/`](aws/) for step-by-step CLI commands covering:
- RDS PostgreSQL instance creation
- S3 bucket setup with encryption + versioning
- ECR repository + Docker image push
- ECS Fargate task definition for Airflow
- IAM least-privilege policy

---

## Vercel Dashboard

See [`dashboard/`](dashboard/) for the Next.js 14 app.
Deploy: connect the repo to Vercel, set `DATABASE_URL` env var, push to main.

---

## Performance: Incremental Load Benchmark

`fact_transactions` is a dbt **incremental** model — each daily run processes only
new rows (via a `created_at` watermark) instead of rebuilding the full history.
Measured on local DuckDB ([details + reproduce](BENCHMARK.md)):

| Base history | Daily delta | Full-refresh | Incremental | **Reduction** |
|---:|---:|---:|---:|---:|
| 1,000,000 | 50,000 | 2.65 s | 0.53 s | **80.0 %** |
| 3,000,000 | 100,000 | 7.64 s | 0.88 s | **88.5 %** |

As history tripled, full-refresh time grew ~linearly while incremental stayed
nearly flat — so the saving **grows with scale**. Both paths are verified to
produce identical row counts (idempotent `delete+insert` on `transaction_id`).

```bash
python benchmarks/benchmark_incremental.py 1000000 50000
```

## Key Numbers

- 1M–3M+ transactions processed per benchmark run (scales to PaySim's 6.36M real rows)
- ~80–88% faster daily fact builds via incremental loading vs full refresh
- 36 Great Expectations checks (bronze) + 48 dbt tests, all gating the pipeline
- SCD Type 2 on `dim_customer` — tracks segment and KYC changes over time
- Full CI pipeline on every PR via GitHub Actions

---

## Interview Talking Points

| Concept             | Answer                                                                 |
|---------------------|------------------------------------------------------------------------|
| SCD Type 2          | `valid_from`, `valid_to`, `is_current` — query customer segment on any date |
| Medallion layers    | Bronze = raw; Silver = cleaned; Gold = star schema. GX gates block bad data |
| Schema drift        | `schema_validator.py` compares columns before bronze load; raises on mismatch |
| dbt incremental     | `unique_key` merge — only new rows; cheaper than full refresh           |
| Data quality gates  | GX checkpoint failure stops Airflow task; downstream never runs         |

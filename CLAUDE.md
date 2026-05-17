# LedgerFlow — Build Guide for Claude

This file governs how Claude builds and deploys the LedgerFlow data warehouse.
**Rule: Ask the user for approval before starting each numbered step.**

---

## Project Summary

LedgerFlow is a retail banking data warehouse with a full medallion architecture
(Bronze → Silver → Gold), dbt transformations, Airflow orchestration, Great
Expectations data quality gates, AWS cloud deployment, and a live Vercel dashboard.

Target: demonstrate a production-grade data engineering stack for portfolio / interviews.

---

## Tech Stack

| Layer              | Tool                                        |
|--------------------|---------------------------------------------|
| Warehouse (local)  | PostgreSQL 15 (Docker)                      |
| Warehouse (prod)   | AWS RDS PostgreSQL 15                       |
| Raw file storage   | AWS S3                                      |
| Transformation     | dbt Core (dbt-postgres)                     |
| Orchestration      | Apache Airflow 2.x (Docker Compose locally, ECS Fargate on AWS) |
| Container registry | AWS ECR                                     |
| Data Quality       | Great Expectations 0.18+                    |
| CI/CD              | GitHub Actions                              |
| Frontend dashboard | Next.js 14 (deployed on Vercel)             |
| Secrets            | AWS Secrets Manager                         |
| IAM                | AWS IAM roles + least-privilege policies    |

---

## Repository Layout (target)

```
ledgerflow-data-warehouse/
├── CLAUDE.md                          ← this file
├── README.md
├── docker-compose.yml                 ← Airflow + local Postgres
├── .env.example                       ← env var template (no secrets)
├── .github/
│   └── workflows/
│       └── ci.yml                     ← GitHub Actions pipeline
├── data_generator/
│   ├── generate_transactions.py
│   ├── generate_customers.py
│   ├── generate_accounts.py
│   └── generate_loans.py
├── ingestion/
│   ├── load_bronze.py
│   └── schema_validator.py
├── dbt_ledgerflow/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── packages.yml
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_transactions.sql
│   │   │   ├── stg_customers.sql
│   │   │   ├── stg_accounts.sql
│   │   │   └── stg_loans.sql
│   │   ├── intermediate/
│   │   │   └── int_customer_accounts.sql
│   │   └── marts/
│   │       ├── fact_transactions.sql
│   │       ├── dim_customer.sql        ← SCD Type 2
│   │       ├── dim_account.sql
│   │       └── dim_product.sql
│   ├── tests/
│   │   ├── assert_no_negative_amounts.sql
│   │   └── assert_scd2_no_overlaps.sql
│   └── macros/
│       └── generate_surrogate_key.sql
├── great_expectations/
│   ├── great_expectations.yml
│   ├── expectations/
│   │   ├── bronze_transactions.json
│   │   ├── bronze_customers.json
│   │   └── silver_transactions.json
│   └── checkpoints/
│       ├── bronze_checkpoint.yml
│       └── silver_checkpoint.yml
├── airflow/
│   └── dags/
│       ├── ledgerflow_daily_dag.py
│       └── ledgerflow_quality_dag.py
├── aws/
│   ├── rds_setup.md                   ← RDS creation commands
│   ├── s3_setup.md                    ← S3 bucket policy
│   ├── ecs_task_definition.json       ← ECS Fargate task for Airflow
│   ├── ecr_push.sh                    ← Build + push Docker image to ECR
│   └── iam_policy.json                ← Least-privilege IAM policy
└── dashboard/                         ← Next.js Vercel app
    ├── package.json
    ├── next.config.js
    ├── vercel.json
    ├── .env.example
    └── app/
        ├── layout.tsx
        ├── page.tsx                   ← KPI overview
        ├── api/
        │   ├── transactions/route.ts  ← proxies RDS query
        │   ├── quality/route.ts       ← GX validation results
        │   └── customers/route.ts
        └── components/
            ├── KpiCards.tsx
            ├── TransactionChart.tsx
            └── QualityBadge.tsx
```

---

## Step-by-Step Build Plan

> **IMPORTANT FOR CLAUDE:**
> Before starting any step, display the step title and description, then ask:
> "Ready to proceed with Step N: <title>? (yes / skip / adjust)"
> Do not execute the step until the user confirms.

---

### STEP 1 — Scaffold Project Structure

**What:** Create all directories and placeholder files so the repo has the
correct shape before any code is written.

**Actions:**
1. Create every directory listed in the layout above using `mkdir`.
2. Write `.env.example` with all required env var names (no values).
3. Write `requirements.txt` covering: faker, pandas, psycopg2-binary,
   dbt-postgres, great_expectations, apache-airflow.
4. Write `docker-compose.yml` with services: `postgres` (15-alpine),
   `airflow-webserver`, `airflow-scheduler`.
5. Update `README.md` with project overview and quick-start commands.

**Done when:** `git status` shows the full folder tree with no missing directories.

---

### STEP 2 — Data Generators

**What:** Python scripts that produce realistic synthetic banking data using Faker.

**Files to write:**
- `data_generator/generate_transactions.py` — 50 000 rows, 3% injected null
  `transaction_date` for GX to catch.
- `data_generator/generate_customers.py` — 1 000 customers with segment
  (RETAIL / PREMIUM / CORPORATE) and kyc_status.
- `data_generator/generate_accounts.py` — 3 000 accounts linked to customers.
- `data_generator/generate_loans.py` — 500 loan records.

**Output:** `data/raw/*.csv` (git-ignored; S3 in production).

**Done when:** `python data_generator/generate_transactions.py` exits 0 and
prints row count + null-date count.

---

### STEP 3 — Bronze Ingestion Layer

**What:** Load raw CSVs into the `bronze` PostgreSQL schema with schema drift
detection before any row lands.

**Files to write:**
- `ingestion/schema_validator.py` — `detect_drift(df, table_name)` function
  that compares DataFrame columns against `EXPECTED_SCHEMAS` dict.
- `ingestion/load_bronze.py` — reads CSV, calls `detect_drift`, adds
  `_loaded_at`, `_source_file`, `_batch_id` metadata columns, then
  `df.to_sql(...)` into the `bronze` schema.

**Done when:** running `python ingestion/load_bronze.py` loads all four tables
into `bronze.*` and prints row counts. Schema drift test: remove a column from
CSV — script must raise `ValueError`.

---

### STEP 4 — dbt Models (Silver + Gold)

**What:** Transform bronze raw data into clean staging views and analytics-ready
star-schema marts.

**Files to write:**

*Configuration*
- `dbt_ledgerflow/dbt_project.yml`
- `dbt_ledgerflow/profiles.yml` (reads from env vars, never hardcoded creds)
- `dbt_ledgerflow/packages.yml` (dbt-utils for surrogate keys)
- `dbt_ledgerflow/macros/generate_surrogate_key.sql`

*Staging (Silver) — materialized as views*
- `stg_transactions.sql` — cast, trim, upper, null filter on PK
- `stg_customers.sql`
- `stg_accounts.sql`
- `stg_loans.sql`

*Intermediate*
- `int_customer_accounts.sql` — join customers ↔ accounts for downstream reuse

*Marts (Gold) — incremental tables*
- `dim_customer.sql` — SCD Type 2 with `valid_from`, `valid_to`, `is_current`
- `dim_account.sql`
- `dim_product.sql`
- `fact_transactions.sql` — joins to all dims, derives `flow_direction`,
  `absolute_amount`

*Tests*
- `assert_no_negative_amounts.sql`
- `assert_scd2_no_overlaps.sql`

**Done when:** `dbt run && dbt test` pass with 0 errors locally.

---

### STEP 5 — Great Expectations Data Quality

**What:** Define 80+ validation rules across bronze and silver layers; wire up
checkpoints that the Airflow DAG will call.

**Files to write:**
- `great_expectations/great_expectations.yml`
- `great_expectations/expectations/bronze_transactions.json` — nulls on PK,
  referential integrity on `transaction_type` / `status`, amount range,
  uniqueness, max-5%-null on `transaction_date`.
- `great_expectations/expectations/bronze_customers.json`
- `great_expectations/expectations/silver_transactions.json`
- `great_expectations/checkpoints/bronze_checkpoint.yml`
- `great_expectations/checkpoints/silver_checkpoint.yml`
- `great_expectations/build_expectations.py` — script that generates suites
  programmatically (run once).

**Done when:** `great_expectations checkpoint run bronze_checkpoint` returns
SUCCESS (some transaction_date nulls hit the 95% threshold — that's expected).

---

### STEP 6 — Airflow DAGs

**What:** Orchestrate the full daily pipeline and quality gate pipeline as two
separate DAGs.

**Files to write:**
- `airflow/dags/ledgerflow_daily_dag.py`
  ```
  generate_data >> load_bronze >> validate_bronze >> run_dbt_staging
  >> validate_silver >> run_dbt_marts >> run_dbt_tests
  ```
- `airflow/dags/ledgerflow_quality_dag.py` — standalone GX checkpoint DAG
  that can run on-demand.
- `docker-compose.yml` — finalize with Airflow env vars, volume mounts for
  dags/, correct Postgres connection string.

**Done when:** `docker-compose up -d` starts cleanly; Airflow UI at
`localhost:8080` shows both DAGs; manual trigger of `ledgerflow_daily_pipeline`
runs end-to-end without task failures.

---

### STEP 7 — GitHub Actions CI/CD

**What:** Automated pipeline that runs on every push to `main` or `dev` and on
every pull request targeting `main`.

**File to write:** `.github/workflows/ci.yml`

**Pipeline steps:**
1. Spin up PostgreSQL 15 service container.
2. `pip install` all dependencies.
3. Generate test data.
4. Load bronze layer.
5. Run GX bronze checkpoint.
6. `dbt deps && dbt run --target ci`.
7. `dbt test`.
8. Run GX silver checkpoint.
9. (On main only) build Docker image and push to AWS ECR.

**Secrets required in GitHub repo settings:**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `ECR_REPOSITORY`
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`

**Done when:** a push to `dev` triggers the workflow and all steps go green in
GitHub Actions.

---

### STEP 8 — AWS Deployment

**What:** Move the stack from local Docker to managed AWS services.

**Sub-steps (each needs user confirmation):**

#### 8a — RDS PostgreSQL
- Create RDS instance: `db.t3.micro`, PostgreSQL 15, Multi-AZ off (cost),
  storage 20 GB gp3.
- VPC: default VPC, security group allows inbound 5432 from ECS only.
- Write connection string to AWS Secrets Manager as `ledgerflow/db`.
- Document commands in `aws/rds_setup.md`.

#### 8b — S3 Data Lake
- Create bucket `ledgerflow-raw-<account-id>` in `us-east-1`.
- Bucket policy: private, versioning on, server-side encryption (AES-256).
- Update `load_bronze.py` to also write CSV to S3 before loading to RDS.
- Document in `aws/s3_setup.md`.

#### 8c — ECR + Docker Image
- Create ECR repository `ledgerflow-airflow`.
- Write `aws/ecr_push.sh` — builds the Airflow Docker image and pushes to ECR.
- GitHub Actions CI (step 7) calls this on merge to main.

#### 8d — ECS Fargate for Airflow
- ECS cluster `ledgerflow-cluster`.
- Task definition in `aws/ecs_task_definition.json` — pulls image from ECR,
  mounts env vars from Secrets Manager, exposes port 8080.
- Service: 1 desired task, assign public IP, security group allows 8080 inbound.
- Document `aws/ecs_setup.md` with `aws ecs` CLI commands.

#### 8e — IAM Policy
- Write `aws/iam_policy.json` — least-privilege: RDS connect, S3 read/write to
  the specific bucket, ECR push/pull, Secrets Manager read for `ledgerflow/*`.
- Attach to a dedicated `ledgerflow-deployer` IAM user (used by CI).

**Done when:**
- Airflow UI is reachable at the ECS task's public IP on port 8080.
- `ledgerflow_daily_pipeline` DAG runs successfully against RDS.
- S3 bucket contains raw CSVs after each run.

---

### STEP 9 — Vercel Dashboard (Next.js 14)

**What:** A public-facing analytics dashboard that reads from the gold layer
(AWS RDS) and visualizes KPIs, transaction trends, and data quality status.

**Pages & components:**

| Route | What it shows |
|-------|--------------|
| `/` | KPI cards: total transactions today, total volume, % failed, avg amount |
| `/transactions` | Paginated table + line chart of daily volume by type |
| `/customers` | Segment breakdown (RETAIL / PREMIUM / CORPORATE) donut chart |
| `/quality` | GX validation result badges per checkpoint run |

**Files to write:**
- `dashboard/package.json` — deps: next, react, recharts, pg (postgres client),
  tailwindcss.
- `dashboard/next.config.js` — image domains, env var exposure.
- `dashboard/vercel.json` — region: `iad1` (closest to `us-east-1` RDS).
- `dashboard/.env.example` — `DATABASE_URL`, `NEXT_PUBLIC_APP_NAME`.
- `dashboard/app/layout.tsx` — shell with nav.
- `dashboard/app/page.tsx` — KPI overview using `KpiCards` component.
- `dashboard/app/api/transactions/route.ts` — server-side API route; queries
  `gold.fact_transactions` via `pg`, returns JSON. Never exposes DB creds to
  browser.
- `dashboard/app/api/quality/route.ts` — reads GX validation results from S3
  (JSON output) and returns latest checkpoint status.
- `dashboard/app/api/customers/route.ts` — segment aggregation query.
- `dashboard/app/components/KpiCards.tsx`
- `dashboard/app/components/TransactionChart.tsx` (Recharts LineChart)
- `dashboard/app/components/QualityBadge.tsx`

**Vercel deployment:**
1. Connect GitHub repo to Vercel project.
2. Set env vars in Vercel dashboard: `DATABASE_URL` (pointing to RDS),
   `NEXT_PUBLIC_APP_NAME=LedgerFlow`.
3. Set RDS security group to allow inbound 5432 from Vercel's static IP range
   (or use a connection pooler like PgBouncer / Neon for edge compatibility).
4. `git push` triggers Vercel deploy automatically.

**Done when:** Vercel deployment URL is live, KPI cards show real numbers from
RDS gold layer, no browser console errors.

---

### STEP 10 — Final Polish & Smoke Test

**What:** End-to-end verification that every layer works together, plus
documentation cleanup.

**Checklist:**
- [ ] Trigger `ledgerflow_daily_pipeline` DAG manually on ECS Airflow.
- [ ] Confirm S3 bucket received new CSVs.
- [ ] Confirm RDS bronze tables updated (row count increased).
- [ ] Confirm dbt incremental run picked up new rows.
- [ ] Confirm GX checkpoints passed (or expected partial failures on nulls).
- [ ] Confirm Vercel dashboard shows updated KPIs within 60s.
- [ ] `dbt docs generate && dbt docs serve` — docs site works locally.
- [ ] `README.md` updated with: architecture diagram description, setup steps,
  Vercel dashboard URL, AWS architecture overview, key interview talking points.
- [ ] All secrets removed from committed files — only `.env.example` present.
- [ ] GitHub Actions CI green on `main`.

**Done when:** all checklist items are ticked.

---

## Environment Variables Reference

```
# Database (local dev)
DB_HOST=localhost
DB_PORT=5432
DB_USER=ledger
DB_PASSWORD=ledger
DB_NAME=ledgerflow

# Database (AWS prod — set in Secrets Manager and Vercel)
DATABASE_URL=postgresql://user:pass@rds-endpoint:5432/ledgerflow

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=ledgerflow-raw-<account-id>
ECR_REPOSITORY=<account-id>.dkr.ecr.us-east-1.amazonaws.com/ledgerflow-airflow

# Vercel / Next.js
NEXT_PUBLIC_APP_NAME=LedgerFlow
```

---

## Interview Talking Points (from spec)

| Concept | One-line answer |
|---------|----------------|
| **SCD Type 2** | New row per change with `valid_from`, `valid_to`, `is_current`; query "what was segment on date X" |
| **Medallion architecture** | Bronze = raw as-is; Silver = cleaned + typed; Gold = star-schema marts. GX gates block promotion on failure |
| **Star schema** | `fact_transactions` in center, FK to `dim_customer`, `dim_account`, `dim_product` |
| **Data quality gates** | GX checkpoint between each layer; critical rule failure stops Airflow downstream tasks |
| **Schema drift** | `schema_validator.py` compares incoming columns before bronze load; raises on missing columns |
| **dbt incremental** | Only new rows processed via `unique_key` merge; cheaper than full refresh |
| **AWS RDS** | Managed PostgreSQL; handles backups, patching, Multi-AZ failover |
| **ECS Fargate** | Serverless containers; Airflow runs without managing EC2 instances |
| **Vercel** | Edge-deployed Next.js; API routes keep DB credentials server-side only |

---

## Key Numbers to Quote

- 500K+ records ingested per day (across 4 sources)
- 80+ GX validation rules
- 4 upstream source tables
- SCD2 on dim_customer tracks segment / KYC changes over time
- 35% reduction in data incidents after quality gates (simulated)
- Dev → staging → prod environment promotion via GitHub Actions

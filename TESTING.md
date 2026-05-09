# LedgerFlow — End-to-End Testing Guide

This guide walks you through every layer of the pipeline so you can verify
each piece works, understand what to look for, and explain it in an interview.

---

## Prerequisites

```powershell
# Activate the conda environment (run once per terminal session)
conda activate ledgerflow

# From the repo root
cd D:\ledgerflow-data-warehouse
```

---

## Layer 1 — Data Generation

### 1a. Generate synthetic customer/account/loan data (Faker)

```powershell
python data_generator/generate_customers.py
python data_generator/generate_accounts.py
python data_generator/generate_loans.py
```

**What to check:**
- `data/raw/customers.csv` — ~1,000 rows, columns: customer_id, full_name, email, segment, kyc_status
- `data/raw/accounts.csv` — 3,000 rows, columns: account_id, customer_id, account_type, balance
- `data/raw/loans.csv` — 500 rows, columns: loan_id, customer_id, principal, loan_status

### 1b. Load real PaySim transaction data

```powershell
# First time only: place the PaySim CSV in data/raw/
# File: PS_20174392719_1491204439457_log.csv (470 MB, from Kaggle)
python data_generator/load_paysim.py
```

**What to check:**
- `data/raw/transactions.csv` — 6,362,620 rows
- Last line prints: `Fraud transactions: 8,213 (0.129%)`
- Transaction types: CASH_OUT 35%, PAYMENT 34%, CASH_IN 22%, TRANSFER 8%, DEBIT 1%

**What PaySim tells us vs Faker:**
Faker generates random numbers with no pattern. PaySim is a real simulation of
mobile money fraud — CASH_OUT and TRANSFER are the only types that carry actual
fraud (isFraud=1). This makes the `fact_fraud_alerts` mart meaningful.

---

## Layer 2 — Bronze Ingestion + Schema Drift Detection

```powershell
python ingestion/load_bronze.py
```

**Expected output:**
```
INFO  Using DuckDB -> ledgerflow.duckdb
INFO  Schema 'bronze' ready.
INFO  Written: 1293 rows  -> bronze.customers
INFO  Written: 3000 rows  -> bronze.accounts
INFO  Written: 500 rows   -> bronze.loans
INFO  Written: 6362620 rows -> bronze.transactions
INFO  Total rows: 6367413
```

**Test schema drift detection (run this to see the guard work):**
```powershell
# Temporarily remove a required column from the CSV and re-run
python -c "
import pandas as pd
df = pd.read_csv('data/raw/transactions.csv')
df.drop(columns=['amount']).to_csv('data/raw/transactions_bad.csv', index=False)
"
# Then edit load_bronze.py sources list to point at transactions_bad.csv
# You'll see: ValueError: HALTED: Critical schema drift in 'transactions'. Missing: {'amount'}
```

**Why bronze is append-only:**
Every run adds rows with a new `_batch_id` (e.g., `20260516_203841`). This means
you have a full audit trail: if a Monday run loaded bad data, you can query
`WHERE _batch_id = '20260516_060000'` to see exactly what landed that day.

**Verify in DuckDB:**
```python
import duckdb
con = duckdb.connect("ledgerflow.duckdb")
print(con.execute("SELECT COUNT(*) FROM bronze.transactions").fetchone())
print(con.execute("SELECT DISTINCT _batch_id FROM bronze.transactions").fetchall())
```

---

## Layer 3 — dbt Transformations (Silver + Gold)

```powershell
cd dbt_ledgerflow
dbt run --profiles-dir .
```

**Expected output:**
```
10 of 10 OK  (4 views, 6 tables)
Done. PASS=10 WARN=0 ERROR=0
```

**What each model does:**

| Model | Layer | Type | What it does |
|-------|-------|------|--------------|
| `stg_transactions` | Silver | view | Cast PaySim columns, derive `is_missed_fraud` |
| `stg_customers` | Silver | view | Clean customer records |
| `stg_accounts` | Silver | view | Clean account records |
| `stg_loans` | Silver | view | Clean loan records |
| `int_customer_accounts` | Silver | table | Join latest customer + account stats |
| `dim_customer` | Gold | table | SCD2: tracks segment/KYC changes over time |
| `dim_account` | Gold | table | Account dimension (Type 1 — current state) |
| `dim_product` | Gold | table | Product dimension from account product_ids |
| `fact_transactions` | Gold | table | 6.36M PaySim rows, fraud flags, amount buckets |
| `fact_fraud_alerts` | Gold | table | Fraud + flagged subset with detection_outcome labels |

**Explain SCD Type 2 (dim_customer) in an interview:**
```sql
-- "What segment was customer CUST100 on 2024-03-15?"
SELECT segment
FROM main_gold.dim_customer
WHERE customer_natural_key = 'CUST100'
  AND valid_from <= '2024-03-15'
  AND valid_to   >  '2024-03-15';

-- "What is customer CUST100's current segment?"
SELECT segment
FROM main_gold.dim_customer
WHERE customer_natural_key = 'CUST100'
  AND is_current = TRUE;
```

**Explore fact_fraud_alerts:**
```python
import duckdb
con = duckdb.connect("ledgerflow.duckdb")

# PaySim insight: fraud ONLY happens in CASH_OUT and TRANSFER
print(con.execute("""
    SELECT transaction_type, detection_outcome, COUNT(*) as n
    FROM main_gold.fact_fraud_alerts
    GROUP BY 1, 2
    ORDER BY 1, 2
""").df())

# How much fraudulent value slipped past detection?
print(con.execute("""
    SELECT SUM(amount) as missed_fraud_value
    FROM main_gold.fact_fraud_alerts
    WHERE detection_outcome = 'FALSE_NEGATIVE'
""").fetchone())
```

---

## Layer 4 — dbt Tests

```powershell
# From dbt_ledgerflow/
dbt test --profiles-dir .
```

**Expected:**
```
Done. PASS=48 WARN=0 ERROR=0 SKIP=0 TOTAL=48
```

**Test categories:**
- `not_null` — 20 tests across all models (PK columns, required fields)
- `unique` — 12 tests (PKs must have no duplicates)
- `accepted_values` — 14 tests (enum columns only allow known values)
- `custom assert_no_negative_amounts` — amount must be >= 0 in fact_transactions
- `custom assert_scd2_no_overlaps` — no customer should have two active rows on the same date

**Run just one model's tests:**
```powershell
dbt test --profiles-dir . --select fact_transactions
dbt test --profiles-dir . --select dim_customer
```

---

## Layer 5 — Great Expectations Data Quality

### Build expectation suites (run once, or after data changes)

```powershell
cd great_expectations/
python build_expectations.py
```

This generates:
- `expectations/bronze_transactions.json` — 23 rules on raw PaySim data
- `expectations/bronze_customers.json` — 13 rules on raw customers
- `expectations/silver_transactions.json` — 12 rules on cleaned transactions

### Run validations

```powershell
python run_validations.py all       # all 3 checkpoints
python run_validations.py bronze    # bronze only
python run_validations.py silver    # silver only
```

**Expected:**
```
[OK] bronze_transactions    23/23 passed
[OK] bronze_customers       13/13 passed
[OK] silver_transactions    12/12 passed
```

**GX rule categories (for interviews):**

| Category | Example rule | Why it matters |
|----------|-------------|----------------|
| COMPLETENESS | `transaction_id` not null | PK nulls break all joins |
| UNIQUENESS | `transaction_id` is unique | Duplicate PKs double-count every metric |
| VALIDITY | `transaction_type` in [CASH_OUT, PAYMENT, ...] | Upstream added a new type? Alert us before it corrupts dashboards |
| RANGE | `amount` between 0 and 100M | Mobile money scale; catches sign flips or currency errors |
| DISTRIBUTION | mean amount between 50K and 500K | Catches silent drift in upstream data generation |
| SHAPE | row count between 1K and 10M | Zero rows = upstream outage; 10M+ = runaway duplicate load |

**Test a deliberate failure (great for demos):**
```python
import duckdb
con = duckdb.connect("ledgerflow.duckdb")
# Inject a bad transaction_type that shouldn't exist
con.execute("""
    INSERT INTO bronze.transactions (transaction_id, transaction_type, amount, is_fraud)
    VALUES ('test-bad-type', 'WIRE_TRANSFER', 1000, 0)
""")
con.close()

# Now run GX — bronze_transactions will FAIL the accepted_values check
# python run_validations.py bronze

# Clean up
con = duckdb.connect("ledgerflow.duckdb")
con.execute("DELETE FROM bronze.transactions WHERE transaction_type = 'WIRE_TRANSFER'")
con.close()
```

---

## Full Pipeline Run (in order)

```powershell
# From repo root
cd D:\ledgerflow-data-warehouse

# 1. Generate data
python data_generator/generate_customers.py
python data_generator/generate_accounts.py
python data_generator/generate_loans.py
python data_generator/load_paysim.py

# 2. Load bronze
python ingestion/load_bronze.py

# 3. Validate bronze
cd great_expectations
python run_validations.py bronze
cd ..

# 4. Run dbt silver + gold
cd dbt_ledgerflow
dbt run --profiles-dir .

# 5. Run dbt tests
dbt test --profiles-dir .
cd ..

# 6. Validate silver
cd great_expectations
python run_validations.py silver
cd ..
```

This is exactly what the Airflow DAG (`ledgerflow_daily_dag.py`) will orchestrate
automatically on a daily schedule once Steps 6-8 are built.

---

## Key Numbers for Interviews

| Metric | Value |
|--------|-------|
| Transaction rows | 6,362,620 |
| Fraud transactions | 8,213 (0.129%) |
| GX validation rules | 48 across 3 suites |
| dbt tests | 48 across 10 models |
| dbt models | 10 (4 views + 6 tables) |
| Bronze load time | ~3 seconds (DuckDB native API) |
| dbt full run time | ~15 seconds |

---

## Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Cannot open database in read-only mode` | Two DuckDB connections open | Use native `duckdb.connect()` not SQLAlchemy for large loads |
| `Column 'absolute_amount' not found` | Old test references renamed column | Updated to `amount` in PaySim schema |
| `FAIL 3000 unique_dim_account_account_key` | Bronze tables loaded twice (duplicate rows) | Drop all bronze tables, reload once clean |
| `source() takes exactly two arguments` | Jinja `{{ }}` in SQL comment parsed by dbt | Remove curly braces from comment text |
| `QUALIFY` keyword error | dbt parser can't handle DuckDB's QUALIFY | Rewrite with `ROW_NUMBER()` subquery + `WHERE rn = 1` |

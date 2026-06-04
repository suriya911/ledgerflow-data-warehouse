# Fusion Warehouse — Scale & Incremental Benchmark

## What this is

LedgerFlow integrates **two heterogeneous payment platforms** into one conformed
star schema:

| Channel | Source | Transactions | Frauds |
|---|---|---:|---:|
| CARD | IBM credit-card dataset | 13,305,915 | 13,332 |
| MOBILE_MONEY | PaySim mobile money | 6,362,620 | 8,213 |
| **Unified `fct_unified_transactions`** | both | **19,668,535** | **21,545** |

Shared (conformed) dimensions: `dim_customer_master` (real IBM demographics —
the shared customer master across both channels), `dim_card`, `dim_merchant`,
`dim_date` (2010–2024), `dim_channel`. FK integrity verified: 0 broken keys.

## Incremental load benchmark (DuckDB, dbt 1.8)

A 200,000-row daily delta lands; the incremental model processes only those rows
via a `txn_timestamp` watermark, vs a full rebuild of all ~19.9M.

| Strategy | Rows processed | dbt model exec time |
|---|---:|---:|
| Full refresh | 19,868,535 | 40.70 s |
| **Incremental** | 200,000 | **5.38 s** |

**Time reduction: 86.8%** — same correct result, a fraction of the compute. Both
paths produce identical row counts.

## Why this matters (interview)

- **Conformed star schema across source systems** — "I integrated a card-issuing
  platform and a mobile-money platform into one fact table with a channel
  dimension and shared customer/date dimensions." (Kimball bus matrix.)
- **You can't naïvely SUM across channels** — different amount semantics (USD card
  vs mobile-money scale), so `dim_channel` keeps them distinct.
- **Scale**: ~19.7M rows from two real datasets.
- **Incremental @ scale**: 86.8% faster daily builds; the saving grows with history.
- **Real-world cleaning**: `$-77.00` string amounts (negatives = refunds), quoted
  commas in the `errors` column, fraud labels in a side JSON, mixed date ranges.

## Reproduce

```bash
# 1. download sources (needs Kaggle token at ~/.kaggle/kaggle.json)
kaggle datasets download -d computingvictor/transactions-fraud-datasets --unzip -p data/raw/ibm
kaggle datasets download -d ealaxi/paysim1 --unzip -p data/raw/paysim
# 2. land both into bronze + build the fused star schema
python ingestion/load_fusion_bronze.py
cd dbt_ledgerflow && dbt run --select fusion --profiles-dir .
```

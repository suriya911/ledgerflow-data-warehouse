# Incremental Load Benchmark — Results

- Base history: **3,000,000** transactions
- Daily delta: **100,000** transactions
- Warehouse: DuckDB (local), dbt incremental `delete+insert` on `transaction_id`
- Correctness: both paths produce **3,100,000** rows — identical.

| Metric | Full refresh | Incremental |
|---|---:|---:|
| dbt model exec time (s) | 7.64 | 0.88 |
| wall-clock time (s) | 12.95 | 6.77 |
| rows processed | 3,100,000 | 100,000 |

**Model-execution time reduction: 88.5%**

**Wall-clock time reduction: 47.7%**

> On each daily run, incremental processes only the new 100,000 rows instead of re-scanning all 3,100,000 — same correct result, a fraction of the compute.

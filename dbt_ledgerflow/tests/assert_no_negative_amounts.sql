-- Custom dbt test: assert_no_negative_amounts
--
-- PaySim amounts are always positive (mobile money platform enforces this).
-- balance_delta CAN be negative (originator's balance decreases on outflow).
-- This test ensures amount itself never goes negative — a data quality invariant.

select
    transaction_id,
    amount
from {{ ref('fact_transactions') }}
where amount < 0

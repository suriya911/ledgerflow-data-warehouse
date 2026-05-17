-- Custom dbt test: assert_no_negative_amounts
--
-- What custom tests are:
--   dbt's built-in tests (not_null, unique, accepted_values) cover basic checks.
--   For business rules, you write a custom test as a SQL query that returns
--   ZERO rows when everything is correct. If it returns ANY rows, the test fails.
--
-- Business rule:
--   absolute_amount is always ABS(amount), so it must never be negative.
--   If it is negative, something went wrong in the derivation logic.
--
-- This also catches a real-world scenario: someone in upstream accidentally
-- stored already-absolute values and our ABS() doubled them.

select
    transaction_id,
    amount,
    absolute_amount
from {{ ref('fact_transactions') }}
where absolute_amount < 0

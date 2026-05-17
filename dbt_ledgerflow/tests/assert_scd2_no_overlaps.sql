-- Custom dbt test: assert_scd2_no_overlaps
--
-- SCD2 correctness rule: for any single customer, their time periods must not overlap.
-- If CUST100 has two rows and both have is_current = true, the SCD2 is broken.
-- If valid_from of row2 is BEFORE valid_to of row1, that's an overlap — also broken.
--
-- How this test works:
--   For each customer, self-join their rows where time periods overlap.
--   A correct SCD2 table returns ZERO rows from this query.
--
-- This test would catch bugs like:
--   - Duplicate inserts (same customer version loaded twice)
--   - Incorrect LEAD() logic (valid_to not set correctly)
--   - Multiple rows with is_current = true for the same customer

select
    a.customer_natural_key,
    a.valid_from                as a_valid_from,
    a.valid_to                  as a_valid_to,
    b.valid_from                as b_valid_from,
    b.valid_to                  as b_valid_to
from {{ ref('dim_customer') }} a
join {{ ref('dim_customer') }} b
    on  a.customer_natural_key = b.customer_natural_key
    and a.customer_key        != b.customer_key          -- different rows
    and a.valid_from           < b.valid_to              -- a starts before b ends
    and a.valid_to             > b.valid_from            -- a ends after b starts

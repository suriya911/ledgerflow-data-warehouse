-- fact_transactions.sql — Central fact table (Gold layer / Star Schema)
--
-- The fact table is the CENTER of the star schema.
-- It stores every transaction event with:
--   - Foreign keys pointing to each dimension (customer, account, product)
--   - Additive measures (amount, absolute_amount) — numbers you can SUM/AVG
--   - Derived attributes (flow_direction, amount_bucket)
--
-- Star schema query pattern:
--   SELECT segment, SUM(amount)
--   FROM gold.fact_transactions f
--   JOIN gold.dim_customer c ON f.customer_key = c.customer_key
--   GROUP BY segment
--
-- Why LEFT JOIN to dims instead of INNER JOIN?
--   LEFT JOIN means: "keep the transaction even if the customer/account
--   dimension row is missing". This prevents silent data loss — you can
--   still see the transaction and investigate the broken FK.
--
-- Materialized as TABLE (largest table in the gold layer).

{{ config(materialized='table') }}

with txns as (

    select * from {{ ref('stg_transactions') }}

),

-- Only join to CURRENT customer records (is_current = true)
-- This gives us the customer's CURRENT segment on the transaction
-- For historical segment at transaction time, use valid_from/valid_to join
dim_cust as (

    select * from {{ ref('dim_customer') }}
    where is_current = true

),

dim_acct as (

    select * from {{ ref('dim_account') }}

),

dim_prod as (

    select * from {{ ref('dim_product') }}

),

final as (

    select
        -- Natural key from source (UUID — unique per transaction)
        t.transaction_id,

        -- Surrogate FK keys linking to dimension tables
        -- NULL if the related dimension row doesn't exist (orphaned FK)
        dc.customer_key,
        da.account_key,
        dp.product_key,

        -- Measures (additive — safe to SUM across any dimension)
        t.amount,
        abs(t.amount)                               as absolute_amount,

        -- Derived attributes
        t.transaction_type,
        t.currency,
        t.merchant_category,
        t.transaction_status,

        -- Classify direction by sign of amount
        -- (separate from transaction_type — a TRANSFER can be positive or negative)
        case
            when t.amount < 0 then 'OUTFLOW'
            else                   'INFLOW'
        end                                         as flow_direction,

        -- Amount bucket for histogram / distribution analysis in dashboards
        case
            when abs(t.amount) < 100      then 'MICRO'
            when abs(t.amount) < 1000     then 'SMALL'
            when abs(t.amount) < 5000     then 'MEDIUM'
            when abs(t.amount) < 10000    then 'LARGE'
            else                               'XLARGE'
        end                                         as amount_bucket,

        -- Date/time for time-series analysis
        t.transaction_date,
        t.created_at,

        -- Denormalized customer attributes (avoids join at query time for common fields)
        dc.segment                                  as customer_segment,
        da.account_type,

        -- Pipeline lineage
        t._batch_id

    from txns t
    left join dim_cust dc on t.customer_id = dc.customer_natural_key
    left join dim_acct da on t.account_id  = da.account_natural_key
    left join dim_prod dp on da.product_id = dp.product_natural_key

)

select * from final

-- fact_transactions.sql — Central fact table with PaySim real data (Gold layer)
--
-- 6.36M rows of real mobile money transaction patterns from PaySim.
-- Star schema center: FK to dim_customer, dim_account, dim_product.
-- Includes fraud fields that power the fact_fraud_alerts mart.
--
-- Materialized as TABLE (largest table in the gold layer).

{{ config(materialized='table') }}

with txns as (

    select * from {{ ref('stg_transactions') }}

),

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
        t.transaction_id,

        -- Surrogate FK keys
        dc.customer_key,
        da.account_key,
        dp.product_key,

        -- Core measures
        t.amount,
        t.balance_before,
        t.balance_after,

        -- Balance delta: how much the originator's balance changed
        (t.balance_after - t.balance_before)    as balance_delta,

        -- PaySim transaction attributes
        t.transaction_type,
        t.currency,
        t.merchant_category,
        t.orig_account_id,
        t.dest_account_id,

        -- Fraud intelligence
        t.is_fraud,
        t.is_flagged_fraud,
        t.is_missed_fraud,   -- fraud that slipped past detection system

        -- Amount buckets (adjusted for mobile money scale)
        case
            when t.amount < 1_000       then 'MICRO'
            when t.amount < 10_000      then 'SMALL'
            when t.amount < 100_000     then 'MEDIUM'
            when t.amount < 1_000_000   then 'LARGE'
            else                             'XLARGE'
        end                                     as amount_bucket,

        -- High-risk flag: large CASH_OUT or TRANSFER (common fraud pattern in PaySim)
        case
            when t.transaction_type in ('CASH_OUT', 'TRANSFER')
             and t.amount > 200_000 then true
            else false
        end                                     as is_high_risk_pattern,

        -- Dates
        t.transaction_date,
        t.created_at,

        -- Denormalized for fast dashboard queries (avoids join at query time)
        dc.segment                              as customer_segment,
        da.account_type,

        t._batch_id

    from txns t
    left join dim_cust dc on t.customer_id = dc.customer_natural_key
    left join dim_acct da on t.account_id  = da.account_natural_key
    left join dim_prod dp on da.product_id = dp.product_natural_key

)

select * from final

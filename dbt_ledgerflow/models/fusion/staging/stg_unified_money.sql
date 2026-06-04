-- stg_unified_money.sql — Silver: PaySim mobile-money transactions harmonized to
-- the unified transaction schema (MOBILE_MONEY channel).
--
-- Entity resolution (the "fusion" step):
--   PaySim's nameOrig (e.g. C1231006815) does not match our customer master.
--   We deterministically map each PaySim sender onto one of the IBM customers
--   (the shared master) via a hash, so both channels share one dim_customer.
--   In a real project this would be a proper identity-resolution service.
--
-- Materialized as a VIEW.

{{ config(materialized='view', schema='silver') }}

with paysim as (
    select *, row_number() over () as _rn
    from {{ source('fusion_bronze', 'paysim_transactions') }}
),

n_customers as (
    select count(*) as cnt from {{ source('fusion_bronze', 'ibm_users') }}
),

-- number the customer master 1..N so we can map a hash onto a real client_id
customer_pool as (
    select id as client_id, row_number() over (order by id) as rn
    from {{ source('fusion_bronze', 'ibm_users') }}
),

mapped as (
    select
        p.*,
        (hash(p.nameOrig) % (select cnt from n_customers)) + 1 as _cust_rn
    from paysim p
),

cleaned as (
    select
        'MM-' || cast(m._rn as varchar)                         as transaction_id,
        'MOBILE_MONEY'                                          as channel,
        cp.client_id                                            as customer_natural_key,
        cast(null as varchar)                                   as card_id,
        cast(null as varchar)                                   as merchant_id,
        cast(null as integer)                                   as mcc,
        case when m.nameDest like 'M%' then 'MERCHANT_PAYMENT'
             else 'P2P_TRANSFER' end                            as merchant_category,

        m.type                                                  as transaction_type,
        cast(null as varchar)                                   as entry_mode,

        cast(m.amount as decimal(18,2))                         as amount,
        abs(cast(m.amount as decimal(18,2)))                    as abs_amount,
        cast(m.oldbalanceOrg as decimal(18,2))                  as balance_before,
        cast(m.newbalanceOrig as decimal(18,2))                 as balance_after,

        (m.isFraud = 1)                                         as is_fraud,
        (m.isFlaggedFraud = 1)                                  as is_flagged_fraud,
        true                                                    as is_fraud_labeled,

        -- PaySim 'step' is 1 hour; anchor the simulation at 2024-01-01
        timestamp '2024-01-01 00:00:00' + (m.step * interval '1 hour') as txn_timestamp,
        cast(timestamp '2024-01-01 00:00:00' + (m.step * interval '1 hour') as date) as txn_date,
        m._batch_id                                             as _batch_id

    from mapped m
    left join customer_pool cp on m._cust_rn = cp.rn
)

select * from cleaned

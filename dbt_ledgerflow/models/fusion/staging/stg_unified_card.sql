-- stg_unified_card.sql — Silver: IBM credit-card transactions harmonized to the
-- unified transaction schema (CARD channel).
--
-- Cleaning done here (real-world messiness = good interview material):
--   - amount is a string like "$-77.00"  -> strip '$', cast to decimal (negatives = refunds)
--   - use_chip ("Swipe/Chip/Online Transaction") -> entry_mode enum
--   - fraud label joined from the separate ibm_fraud_labels table (Yes/No -> boolean)
--   - mcc joined to its human-readable category
-- Materialized as a VIEW (zero storage, always fresh).

{{ config(materialized='view', schema='silver') }}

with txns as (
    select * from {{ source('fusion_bronze', 'ibm_transactions') }}
),

labels as (
    select transaction_id, fraud_label from {{ source('fusion_bronze', 'ibm_fraud_labels') }}
),

mcc as (
    select mcc, mcc_category from {{ source('fusion_bronze', 'ibm_mcc') }}
),

cleaned as (
    select
        'CARD-' || cast(t.id as varchar)                         as transaction_id,
        'CARD'                                                   as channel,
        t.client_id                                             as customer_natural_key,
        cast(t.card_id as varchar)                              as card_id,
        cast(t.merchant_id as varchar)                          as merchant_id,
        t.mcc                                                   as mcc,
        coalesce(m.mcc_category, 'UNKNOWN')                     as merchant_category,

        -- Business type derived from amount sign; card entry mode kept separately
        case when cast(replace(t.amount, '$', '') as decimal(18,2)) < 0
             then 'REFUND' else 'PURCHASE' end                  as transaction_type,
        case t.use_chip
            when 'Swipe Transaction'  then 'SWIPE'
            when 'Chip Transaction'   then 'CHIP'
            when 'Online Transaction' then 'ONLINE'
            else 'OTHER'
        end                                                     as entry_mode,

        cast(replace(t.amount, '$', '') as decimal(18,2))       as amount,
        abs(cast(replace(t.amount, '$', '') as decimal(18,2)))  as abs_amount,

        -- Card transactions carry no running balance in this dataset
        cast(null as decimal(18,2))                             as balance_before,
        cast(null as decimal(18,2))                             as balance_after,

        (l.fraud_label = 'Yes')                                 as is_fraud,
        cast(null as boolean)                                   as is_flagged_fraud,
        (l.transaction_id is not null)                          as is_fraud_labeled,

        t.date                                                  as txn_timestamp,
        cast(t.date as date)                                    as txn_date,
        t._batch_id                                             as _batch_id

    from txns t
    left join labels l on t.id  = l.transaction_id
    left join mcc    m on t.mcc = m.mcc
)

select * from cleaned

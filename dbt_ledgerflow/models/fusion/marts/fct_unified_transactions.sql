-- fct_unified_transactions.sql — Gold: the UNIFIED fact table.
--
-- This is the payoff of the fusion: ~19.7M transactions from two heterogeneous
-- source systems (IBM card + PaySim mobile money) in ONE conformed star schema,
-- distinguished by dim_channel and sharing dim_customer_master / dim_date /
-- dim_merchant / dim_card.
--
-- Incremental: a created_at-style watermark (txn_timestamp) means daily runs only
-- process new rows instead of rebuilding all 19.7M (see benchmarks/).

{{
  config(
    materialized='incremental',
    unique_key='transaction_id',
    incremental_strategy='delete+insert',
    schema='gold'
  )
}}

with unified as (
    select * from {{ ref('stg_unified_card') }}
    union all by name
    select * from {{ ref('stg_unified_money') }}
),

filtered as (
    select * from unified
    {% if is_incremental() %}
    where txn_timestamp > (select coalesce(max(txn_timestamp), timestamp '1900-01-01') from {{ this }})
    {% endif %}
)

select
    u.transaction_id,

    -- Conformed dimension foreign keys
    ch.channel_key,
    cust.customer_key,
    card.card_key,                                       -- null for mobile money
    mer.merchant_key,                                    -- null for P2P transfers
    dd.date_key,

    -- Attributes
    u.channel,
    u.transaction_type,
    u.entry_mode,
    u.merchant_category,

    -- Measures
    u.amount,
    u.abs_amount,
    u.balance_before,
    u.balance_after,
    (u.balance_after - u.balance_before)                as balance_delta,   -- mobile money only

    -- Fraud intelligence
    u.is_fraud,
    u.is_flagged_fraud,
    u.is_fraud_labeled,
    case
        when u.abs_amount > 200000
         and u.transaction_type in ('CASH_OUT', 'TRANSFER') then true
        else false
    end                                                 as is_high_risk,

    -- Dates
    u.txn_timestamp,
    u.txn_date,
    u._batch_id

from filtered u
left join {{ ref('dim_channel') }}          ch   on u.channel              = ch.channel
left join {{ ref('dim_customer_master') }}  cust on u.customer_natural_key = cust.customer_natural_key
left join {{ ref('dim_card') }}             card on u.card_id              = cast(card.card_natural_key as varchar)
left join {{ ref('dim_merchant') }}         mer  on u.merchant_id          = mer.merchant_natural_key
left join {{ ref('dim_date') }}             dd   on u.txn_date             = dd.date_key

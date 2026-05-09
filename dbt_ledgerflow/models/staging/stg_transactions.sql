-- stg_transactions.sql — Silver layer: clean and type PaySim transactions
--
-- Source: PaySim financial fraud simulation dataset (6.36M rows)
-- Mapped from raw PaySim columns by data_generator/load_paysim.py
--
-- Key differences from synthetic Faker data:
--   - No 'status' column (PaySim doesn't have transaction status)
--   - Added balance_before/after columns (real banking context)
--   - Added is_fraud / is_flagged_fraud flags (drives fact_fraud_alerts mart)
--   - transaction_type values: CASH_OUT, PAYMENT, CASH_IN, TRANSFER, DEBIT
--   - Amounts are mobile money scale (avg ~$179K, max ~$92M)
--
-- Materialized as VIEW (always fresh, zero storage cost).

{{ config(materialized='view') }}

with source as (

    select * from {{ source('bronze', 'transactions') }}

),

cleaned as (

    select
        transaction_id,
        account_id,
        customer_id,

        -- PaySim type normalization (already uppercase, just trim whitespace)
        upper(trim(transaction_type))       as transaction_type,
        upper(trim(currency))               as currency,
        upper(trim(merchant_category))      as merchant_category,

        -- Financial amounts — PaySim uses mobile money scale (large values are normal)
        cast(amount as decimal(18, 2))          as amount,
        cast(balance_before as decimal(18, 2))  as balance_before,
        cast(balance_after as decimal(18, 2))   as balance_after,
        cast(dest_balance_before as decimal(18, 2)) as dest_balance_before,
        cast(dest_balance_after as decimal(18, 2))  as dest_balance_after,

        -- PaySim account identifiers (C = customer, M = merchant prefix)
        orig_account_id,
        dest_account_id,

        -- Fraud flags (cast to boolean for clarity)
        cast(is_fraud as boolean)           as is_fraud,
        cast(is_flagged_fraud as boolean)   as is_flagged_fraud,

        -- Fraud detection gap: transactions flagged but NOT actual fraud (false positives)
        -- and transactions that ARE fraud but were NOT flagged (missed detections)
        case
            when cast(is_fraud as boolean) = true
             and cast(is_flagged_fraud as boolean) = false then true
            else false
        end                                 as is_missed_fraud,

        -- Dates
        cast(transaction_date as date)      as transaction_date,
        cast(created_at as timestamp)       as created_at,

        -- Audit columns
        _loaded_at,
        _batch_id

    from source

    -- Basic dedup guard on primary key
    where transaction_id is not null
      and amount is not null
      and amount > 0   -- PaySim only has positive amounts (direction encoded in type)

)

select * from cleaned

-- stg_transactions.sql — Silver layer: clean and type raw transactions
--
-- What this model does step by step:
--   1. Pull from bronze.transactions (the raw landing table)
--   2. Cast every column to its correct data type
--      (bronze stores everything as text to avoid load failures)
--   3. Normalize strings: UPPER() + TRIM() so "debit", "DEBIT", " Debit " all
--      become "DEBIT" — consistent values that GX and dbt tests can validate
--   4. Filter out rows where transaction_id IS NULL (dedup guard —
--      if the same bad row was loaded twice, only take non-null PKs)
--   5. Expose only the columns downstream models should use
--      (_source_file and _loaded_at are internal audit columns, kept via _batch_id)
--
-- Materialized as VIEW so it's always up to date with whatever is in bronze.
-- No storage cost — every time you query silver.stg_transactions, this SQL runs.

{{ config(materialized='view') }}

with source as (

    -- source() resolves to bronze.transactions and registers lineage in dbt
    select * from {{ source('bronze', 'transactions') }}

),

cleaned as (

    select
        transaction_id,
        account_id,
        customer_id,

        -- Normalize free-text enums — removes whitespace and uppercases
        upper(trim(transaction_type))   as transaction_type,
        upper(trim(currency))           as currency,
        upper(trim(merchant_category))  as merchant_category,
        upper(trim(status))             as transaction_status,

        -- Cast to correct types
        -- Bronze stores amounts as text; cast here once so all downstream
        -- models get numeric arithmetic without repeating the cast.
        cast(amount as decimal(18, 2))  as amount,

        -- transaction_date has ~3% nulls — we keep them (GX will flag them)
        -- Casting NULL stays NULL; no coalesce here — silver preserves truth
        cast(transaction_date as date)  as transaction_date,

        cast(created_at as timestamp)   as created_at,

        -- Audit columns from load_bronze.py — useful for debugging data lineage
        _loaded_at,
        _batch_id

    from source

    -- Basic dedup guard: reject rows with no natural key
    -- Real dedup (by transaction_id) happens in fact_transactions using unique_key
    where transaction_id is not null
      and amount        is not null

)

select * from cleaned

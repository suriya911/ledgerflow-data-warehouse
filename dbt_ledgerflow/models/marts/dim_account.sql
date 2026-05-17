-- dim_account.sql — Account dimension (Gold layer)
--
-- Accounts are treated as Type 1 (overwrite) — we only need the current state.
-- A surrogate key is generated from account_id so fact_transactions can join
-- consistently even if account_id format changes in the future.
--
-- Materialized as TABLE.

{{ config(materialized='table') }}

with source as (

    select * from {{ ref('stg_accounts') }}

),

final as (

    select
        -- Surrogate key for clean FK joins in the fact table
        {{ generate_surrogate_key(['account_id']) }}    as account_key,

        account_id                                      as account_natural_key,
        customer_id,
        account_type,
        balance,
        opened_date,
        account_status,
        product_id,

        -- Derived attributes useful in dashboards
        case
            when balance >= 50000   then 'HIGH'
            when balance >= 5000    then 'MEDIUM'
            when balance >= 0       then 'LOW'
            else                         'NEGATIVE'   -- loan accounts
        end                                             as balance_tier,

        -- Account age in full years (for cohort analysis)
        cast(
            (current_date - opened_date) / 365
        as integer)                                     as account_age_years

    from source

)

select * from final

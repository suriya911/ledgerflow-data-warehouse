-- stg_accounts.sql — Silver layer: clean and type raw account records
--
-- Accounts are mostly static (accounts don't change often).
-- We cast balance to numeric and opened_date to a proper date type.
-- product_id links to dim_product in the gold layer.

{{ config(materialized='view') }}

with source as (

    select * from {{ source('bronze', 'accounts') }}

),

cleaned as (

    select
        account_id,
        customer_id,

        upper(trim(account_type))        as account_type,   -- CHECKING / SAVINGS / LOAN

        -- balance can be negative for LOAN accounts
        cast(balance as decimal(18, 2))  as balance,

        cast(opened_date as date)        as opened_date,

        upper(trim(status))              as account_status,

        product_id

    from source

    where account_id is not null

)

select * from cleaned

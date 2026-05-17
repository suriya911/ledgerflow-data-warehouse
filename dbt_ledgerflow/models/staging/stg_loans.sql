-- stg_loans.sql — Silver layer: clean and type raw loan records
--
-- Loans have financial precision requirements:
--   principal and interest_rate need decimal(18,4) not float
--   to avoid floating-point rounding errors in interest calculations.

{{ config(materialized='view') }}

with source as (

    select * from {{ source('bronze', 'loans') }}

),

cleaned as (

    select
        loan_id,
        customer_id,
        account_id,

        -- Financial fields: use decimal, not float, for exact arithmetic
        cast(principal as decimal(18, 2))       as principal,
        cast(interest_rate as decimal(6, 4))    as interest_rate,

        cast(term_months as integer)            as term_months,

        cast(disbursement_date as date)         as disbursement_date,
        cast(maturity_date as date)             as maturity_date,

        upper(trim(status))                     as loan_status

    from source

    where loan_id    is not null
      and principal  is not null

)

select * from cleaned

-- stg_customers.sql — Silver layer: clean and type raw customer records
--
-- Key point: this staging model retains ALL rows including historical versions.
-- A customer who changed segment appears TWICE here (two updated_at values).
-- The SCD2 logic (valid_from / valid_to / is_current) is applied downstream
-- in dim_customer, not here. Staging just cleans. It doesn't make decisions.
--
-- Materialized as VIEW (always fresh, zero storage).

{{ config(materialized='view') }}

with source as (

    select * from {{ source('bronze', 'customers') }}

),

cleaned as (

    select
        customer_id,

        -- Trim whitespace that Faker sometimes injects into names
        trim(full_name)                 as full_name,

        -- Lowercase email for consistent joins (email is case-insensitive)
        lower(trim(email))              as email,

        trim(phone)                     as phone,
        trim(address)                   as address,

        -- Normalize enums
        upper(trim(segment))            as segment,
        upper(trim(kyc_status))         as kyc_status,

        cast(created_at as timestamp)   as created_at,
        cast(updated_at as timestamp)   as updated_at

    from source

    where customer_id is not null

)

select * from cleaned

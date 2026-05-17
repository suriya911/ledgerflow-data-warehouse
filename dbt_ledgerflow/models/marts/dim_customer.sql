-- dim_customer.sql — SCD Type 2 customer dimension (Gold layer)
--
-- SCD2 in plain English:
--   When a customer changes (different segment, KYC update), we don't overwrite.
--   We CLOSE the old row (stamp valid_to) and INSERT a new row.
--   This way we can answer: "What was CUST100's segment on 2024-03-15?"
--   Answer: find the row where valid_from <= '2024-03-15' <= valid_to
--
-- How the window function works here:
--   LEAD(updated_at) OVER (PARTITION BY customer_id ORDER BY updated_at)
--   For each row, "look at the NEXT row for this customer (by date)"
--   If there IS a next row -> that next row's updated_at becomes THIS row's valid_to
--   If there is NO next row -> this is the CURRENT row -> valid_to = '9999-12-31'
--
-- Surrogate key = MD5(customer_id + updated_at)
--   Stable, unique per version. fact_transactions joins to this key.
--
-- Materialized as TABLE (physical storage in gold schema)

{{ config(materialized='table') }}

with source as (

    select * from {{ ref('stg_customers') }}

),

scd2 as (

    select
        -- Surrogate key: unique per customer VERSION (not per customer)
        {{ generate_surrogate_key(['customer_id', 'updated_at']) }}
                                                    as customer_key,

        customer_id                                 as customer_natural_key,

        full_name,
        email,
        phone,
        address,
        segment,
        kyc_status,

        -- SCD2 time window columns
        -- valid_from = when this version became active
        updated_at                                  as valid_from,

        -- valid_to = when the NEXT version superseded this one
        -- LEAD() looks forward in the partition — if no next row, use sentinel date
        coalesce(
            lead(updated_at) over (
                partition by customer_id
                order by updated_at
            ),
            cast('9999-12-31' as timestamp)
        )                                           as valid_to,

        -- is_current = true only for the row with no successor
        case
            when lead(updated_at) over (
                partition by customer_id
                order by updated_at
            ) is null then true
            else false
        end                                         as is_current,

        created_at

    from source

)

select * from scd2

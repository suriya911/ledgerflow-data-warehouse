-- dim_product.sql — Product dimension (Gold layer)
--
-- We don't have a dedicated products source table (a real bank would have one).
-- Instead, we derive the product dimension from the distinct product_ids in accounts.
-- In a real system you'd JOIN to a product catalog API or table.
--
-- This pattern (deriving a dimension from a fact attribute) is common when
-- a source system doesn't export lookup tables separately.
--
-- Materialized as TABLE.

{{ config(materialized='table') }}

with products as (

    -- Extract distinct product IDs from accounts
    select distinct
        product_id
    from {{ ref('stg_accounts') }}
    where product_id is not null

),

enriched as (

    select
        {{ generate_surrogate_key(['product_id']) }}    as product_key,

        product_id                                      as product_natural_key,

        -- Simulate a product catalog based on the ID number
        -- PROD001-005 = basic, 006-010 = premium, 011-015 = corporate, 016-020 = specialized
        case
            when cast(replace(product_id, 'PROD', '') as integer) between 1  and 5  then 'BASIC'
            when cast(replace(product_id, 'PROD', '') as integer) between 6  and 10 then 'PREMIUM'
            when cast(replace(product_id, 'PROD', '') as integer) between 11 and 15 then 'CORPORATE'
            else                                                                          'SPECIALIZED'
        end                                             as product_tier,

        case
            when cast(replace(product_id, 'PROD', '') as integer) between 1  and 5  then 'Entry-level banking product'
            when cast(replace(product_id, 'PROD', '') as integer) between 6  and 10 then 'Premium banking product with benefits'
            when cast(replace(product_id, 'PROD', '') as integer) between 11 and 15 then 'Corporate treasury product'
            else                                                                          'Specialized financial instrument'
        end                                             as product_description,

        -- Monthly fee tier (simulated)
        case
            when cast(replace(product_id, 'PROD', '') as integer) between 1  and 5  then 0.00
            when cast(replace(product_id, 'PROD', '') as integer) between 6  and 10 then 9.99
            when cast(replace(product_id, 'PROD', '') as integer) between 11 and 15 then 49.99
            else                                                                          99.99
        end                                             as monthly_fee

    from products

)

select * from enriched

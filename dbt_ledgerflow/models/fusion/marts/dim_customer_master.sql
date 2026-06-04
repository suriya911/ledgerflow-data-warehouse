-- dim_customer_master.sql — Gold: the SHARED customer master (conformed across
-- both channels). Built from IBM users_data (real demographics). PaySim
-- transactions are mapped onto these customers in stg_unified_money.
--
-- SCD2 structure is retained (valid_from / valid_to / is_current) so the design
-- supports change tracking; this source has one row per customer, so all rows
-- are the current version.

{{ config(materialized='table', schema='gold') }}

select
    md5(cast(id as varchar))                                as customer_key,
    id                                                      as customer_natural_key,
    current_age,
    retirement_age,
    gender,
    address,
    latitude,
    longitude,
    cast(replace(per_capita_income, '$', '') as decimal(18,2)) as per_capita_income,
    cast(replace(yearly_income,     '$', '') as decimal(18,2)) as yearly_income,
    cast(replace(total_debt,        '$', '') as decimal(18,2)) as total_debt,
    credit_score,
    num_credit_cards,

    -- SCD2 columns (single current version per customer here)
    timestamp '1900-01-01'                                  as valid_from,
    cast(null as timestamp)                                 as valid_to,
    true                                                    as is_current

from {{ source('fusion_bronze', 'ibm_users') }}

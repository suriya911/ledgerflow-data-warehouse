-- dim_merchant.sql — Gold: merchant dimension (CARD channel only).
-- Built from distinct merchants seen in IBM transactions, enriched with the MCC
-- category. Mobile-money P2P transfers have no merchant -> NULL merchant_key.
--
-- A merchant_id can appear with more than one mcc/city across rows; we collapse
-- to one row per merchant using min() for deterministic surrogate keys.

{{ config(materialized='table', schema='gold') }}

with merchants as (
    select
        merchant_id,
        min(mcc)            as mcc,
        min(merchant_city)  as merchant_city,
        min(merchant_state) as merchant_state
    from {{ source('fusion_bronze', 'ibm_transactions') }}
    where merchant_id is not null
    group by merchant_id
)

select
    md5(cast(m.merchant_id as varchar))         as merchant_key,
    cast(m.merchant_id as varchar)              as merchant_natural_key,
    m.mcc,
    coalesce(c.mcc_category, 'UNKNOWN')         as merchant_category,
    m.merchant_city,
    m.merchant_state
from merchants m
left join {{ source('fusion_bronze', 'ibm_mcc') }} c on m.mcc = c.mcc

-- dim_card.sql — Gold: payment-card dimension (CARD channel only).
-- Mobile-money transactions have no card, so they get a NULL card_key in the fact.

{{ config(materialized='table', schema='gold') }}

select
    md5(cast(id as varchar))                                as card_key,
    id                                                      as card_natural_key,
    client_id                                               as customer_natural_key,
    card_brand,
    card_type,
    has_chip,
    num_cards_issued,
    cast(replace(credit_limit, '$', '') as decimal(18,2))   as credit_limit,
    card_on_dark_web

from {{ source('fusion_bronze', 'ibm_cards') }}

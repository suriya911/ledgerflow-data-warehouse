-- dim_channel.sql — Gold: the conformed dimension that distinguishes the two
-- integrated source systems. This is what makes the union meaningful: you never
-- naively SUM across channels because their amount semantics differ.

{{ config(materialized='table', schema='gold') }}

select 1 as channel_key, 'CARD'         as channel, 'IBM credit-card issuing platform'   as description, 'USD'   as currency_basis
union all
select 2 as channel_key, 'MOBILE_MONEY' as channel, 'PaySim mobile-money platform'        as description, 'LOCAL' as currency_basis

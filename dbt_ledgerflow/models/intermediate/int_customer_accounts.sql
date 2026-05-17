-- int_customer_accounts.sql — Intermediate layer
--
-- Joins customers (latest version only) to their account stats.
-- Rewritten without QUALIFY for dbt SQL parser compatibility.
-- Logic: use ROW_NUMBER() in a subquery, then filter to rank=1.

{{ config(materialized='table') }}

with customers_ranked as (

    -- Assign a rank per customer: rank 1 = most recently updated record
    select
        customer_id,
        full_name,
        email,
        segment,
        kyc_status,
        updated_at,
        row_number() over (
            partition by customer_id
            order by updated_at desc
        ) as rn
    from {{ ref('stg_customers') }}

),

customers as (

    -- Keep only the current (latest) version per customer
    select
        customer_id,
        full_name,
        email,
        segment,
        kyc_status,
        updated_at
    from customers_ranked
    where rn = 1

),

accounts as (

    select * from {{ ref('stg_accounts') }}

),

account_stats as (

    select
        customer_id,
        count(*)                                        as total_accounts,
        sum(balance)                                    as total_balance,
        max(case when account_type = 'LOAN'     then 1 else 0 end) as has_loan,
        max(case when account_type = 'CHECKING' then 1 else 0 end) as has_checking,
        max(case when account_type = 'SAVINGS'  then 1 else 0 end) as has_savings
    from accounts
    group by customer_id

)

select
    c.customer_id,
    c.full_name,
    c.email,
    c.segment,
    c.kyc_status,
    a.total_accounts,
    a.total_balance,
    a.has_loan,
    a.has_checking,
    a.has_savings,

    case
        when a.total_balance >= 100000 then 'HIGH_VALUE'
        when a.total_balance >= 10000  then 'MID_VALUE'
        else                                'STANDARD'
    end as value_tier

from customers c
left join account_stats a on c.customer_id = a.customer_id

-- dim_date.sql — Gold: conformed date dimension spanning BOTH source systems
-- (IBM 2010–2019, PaySim anchored at 2024). A single date dimension shared by
-- every channel is the textbook example of a conformed dimension.

{{ config(materialized='table', schema='gold') }}

with spine as (
    select unnest(generate_series(date '2010-01-01', date '2024-12-31', interval '1 day')) as d
)

select
    cast(d as date)                              as date_key,
    extract(year    from d)                      as year,
    extract(quarter from d)                      as quarter,
    extract(month   from d)                      as month,
    extract(day     from d)                      as day,
    extract(dayofweek from d)                    as day_of_week,
    strftime(d, '%B')                            as month_name,
    case when extract(dayofweek from d) in (0, 6) then true else false end as is_weekend
from spine

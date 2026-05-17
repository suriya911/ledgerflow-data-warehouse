-- generate_surrogate_key macro
--
-- What is a surrogate key?
--   A surrogate key is an artificial primary key we create for dimension tables.
--   Why not use the natural key (like customer_id)?
--   Because in SCD2, the same customer_id appears multiple times (one row per
--   version of the record). We need a UNIQUE key per row, not per customer.
--   Solution: hash customer_id + updated_at together -> unique surrogate key.
--
-- This macro wraps dbt_utils.generate_surrogate_key for convenience.
-- dbt_utils hashes the concatenated column values using MD5.
--
-- Usage:
--   {{ generate_surrogate_key(['customer_id', 'updated_at']) }}
--   -> produces: md5(customer_id || '-' || updated_at)
--
-- We keep this wrapper so we can swap the hashing algorithm later without
-- touching every model file.

{% macro generate_surrogate_key(field_list) %}
    {{ dbt_utils.generate_surrogate_key(field_list) }}
{% endmacro %}

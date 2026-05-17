-- fact_fraud_alerts.sql — Fraud analysis mart (Gold layer)
--
-- This mart exists because of real PaySim data — synthetic Faker data
-- couldn't produce meaningful fraud patterns.
--
-- What this answers:
--   1. What % of fraud transactions were caught by the flag system?
--      -> SELECT AVG(CASE WHEN is_flagged_fraud THEN 1 ELSE 0 END) FROM fact_fraud_alerts
--   2. Which transaction types carry the most fraud?
--      -> SELECT transaction_type, COUNT(*) FROM fact_fraud_alerts GROUP BY 1
--   3. What is the total fraudulent value at risk?
--      -> SELECT SUM(amount) FROM fact_fraud_alerts WHERE is_fraud
--   4. How many high-value frauds slipped through detection?
--      -> SELECT COUNT(*) FROM fact_fraud_alerts WHERE is_missed_fraud AND amount > 100000
--
-- PaySim insight: fraud ONLY occurs in CASH_OUT and TRANSFER types.
-- The flag system (isFlaggedFraud) has a very high false-positive rate —
-- it flags many legitimate large transfers as fraud.
--
-- Materialized as TABLE (used heavily by dashboard and GX quality checks).

{{ config(materialized='table') }}

with fraud_txns as (

    -- Only include transactions that are either actual fraud OR flagged as fraud
    -- (to capture both true positives and false positives in one mart)
    select *
    from {{ ref('fact_transactions') }}
    where is_fraud = true
       or is_flagged_fraud = true

),

final as (

    select
        transaction_id,
        customer_key,
        account_key,

        transaction_type,
        amount,
        balance_before,
        balance_after,
        balance_delta,
        orig_account_id,
        dest_account_id,

        -- Fraud classification
        is_fraud,
        is_flagged_fraud,
        is_missed_fraud,

        -- Detection outcome label (useful for dashboards and ML feature engineering)
        case
            when is_fraud = true  and is_flagged_fraud = true  then 'TRUE_POSITIVE'
            when is_fraud = false and is_flagged_fraud = true  then 'FALSE_POSITIVE'
            when is_fraud = true  and is_flagged_fraud = false then 'FALSE_NEGATIVE'
            else                                                    'TRUE_NEGATIVE'
        end                                     as detection_outcome,

        amount_bucket,
        is_high_risk_pattern,
        transaction_date,
        created_at,
        customer_segment,
        _batch_id

    from fraud_txns

)

select * from final

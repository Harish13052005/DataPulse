-- ============================================================================
-- Query: RFM (Recency, Frequency, Monetary) Customer Segmentation
-- Identifies customer tiers: Champions, Loyal Customers, At Risk, Lost
-- ============================================================================

WITH customer_aggregates AS (
    SELECT 
        c.customer_id,
        c.full_name,
        c.email,
        c.customer_segment,
        c.state,
        c.signup_date,
        MAX(o.order_timestamp) AS last_order_date,
        COUNT(o.order_key) AS frequency,
        COALESCE(SUM(o.net_amount), 0.0) AS monetary,
        COALESCE(AVG(o.net_amount), 0.0) AS avg_order_value
    FROM dim_customers c
    LEFT JOIN fact_orders o 
        ON c.customer_key = o.customer_key 
        AND o.status = 'COMPLETED'
    GROUP BY 
        c.customer_id, c.full_name, c.email, c.customer_segment, c.state, c.signup_date
),
ref_date AS (
    SELECT COALESCE(MAX(order_timestamp), CURRENT_TIMESTAMP) AS max_dt 
    FROM fact_orders
),
rfm_metrics AS (
    SELECT 
        ca.*,
        ROUND(
            (EXTRACT(EPOCH FROM (rd.max_dt - COALESCE(ca.last_order_date, CAST(ca.signup_date AS TIMESTAMP)))) / 86400.0)
        ) AS recency_days
    FROM customer_aggregates ca
    CROSS JOIN ref_date rd
)
SELECT 
    customer_id,
    full_name,
    email,
    customer_segment,
    state,
    signup_date,
    last_order_date,
    recency_days,
    frequency,
    ROUND(CAST(monetary AS NUMERIC), 2) AS monetary,
    ROUND(CAST(avg_order_value AS NUMERIC), 2) AS avg_order_value,
    CASE 
        WHEN frequency >= 4 AND monetary >= 1500 THEN 'Champions'
        WHEN frequency >= 3 AND monetary >= 800 THEN 'Loyal Customers'
        WHEN frequency >= 2 AND recency_days <= 90 THEN 'Potential Loyalists'
        WHEN frequency = 1 AND recency_days <= 60 THEN 'New Customers'
        WHEN frequency >= 2 AND recency_days > 120 THEN 'At Risk'
        WHEN frequency = 0 THEN 'Never Purchased'
        ELSE 'Needs Attention'
    END AS rfm_segment
FROM rfm_metrics
ORDER BY monetary DESC, frequency DESC;

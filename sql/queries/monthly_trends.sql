-- ============================================================================
-- Query: Monthly Revenue Trends and Month-over-Month (MoM) Growth
-- Calculates gross sales, discounts, net revenue, and percentage growth
-- ============================================================================

WITH monthly_summary AS (
    SELECT 
        d.year,
        d.month_num,
        d.year || '-' || CASE WHEN d.month_num < 10 THEN '0' || d.month_num ELSE '' || d.month_num END AS year_month,
        COUNT(o.order_key) AS total_orders,
        SUM(CASE WHEN o.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_orders,
        SUM(CASE WHEN o.status = 'REFUNDED' THEN 1 ELSE 0 END) AS refunded_orders,
        ROUND(SUM(o.subtotal), 2) AS gross_revenue,
        ROUND(SUM(o.discount_amount), 2) AS total_discounts,
        ROUND(SUM(o.tax_amount), 2) AS total_taxes,
        ROUND(SUM(o.shipping_fee), 2) AS total_shipping,
        ROUND(SUM(o.net_amount), 2) AS net_revenue,
        ROUND(AVG(o.net_amount), 2) AS average_order_value
    FROM fact_orders o
    JOIN dim_date d ON o.order_date_key = d.date_key
    GROUP BY d.year, d.month_num
    ORDER BY d.year ASC, d.month_num ASC
)
SELECT 
    year,
    month_num,
    year_month,
    total_orders,
    completed_orders,
    refunded_orders,
    gross_revenue,
    total_discounts,
    net_revenue,
    average_order_value,
    ROUND(
        ((net_revenue - LAG(net_revenue, 1) OVER (ORDER BY year, month_num)) / 
        NULLIF(LAG(net_revenue, 1) OVER (ORDER BY year, month_num), 0.0)) * 100.0, 
        2
    ) AS mom_growth_pct
FROM monthly_summary
ORDER BY year_month ASC;

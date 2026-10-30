-- ============================================================================
-- Query: Product Performance and Category Breakdown
-- Identifies top margin and volume products
-- ============================================================================

SELECT 
    p.product_id,
    p.product_name,
    p.category,
    p.price_tier,
    p.unit_price,
    COUNT(DISTINCT oi.order_key) AS total_orders,
    SUM(oi.quantity) AS total_units_sold,
    ROUND(SUM(oi.line_total), 2) AS gross_sales,
    ROUND(SUM(oi.discount_allocated), 2) AS total_discounts,
    ROUND(SUM(oi.line_total - oi.discount_allocated), 2) AS net_sales
FROM fact_order_items oi
JOIN dim_products p ON oi.product_key = p.product_key
JOIN fact_orders o ON oi.order_key = o.order_key
WHERE o.status = 'COMPLETED'
GROUP BY p.product_id, p.product_name, p.category, p.price_tier, p.unit_price
ORDER BY net_sales DESC;

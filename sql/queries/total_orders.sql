-- Query: Total Orders
-- Business purpose: Count the total number of distinct orders in the system.
SELECT COUNT(DISTINCT order_id) AS total_orders
FROM warehouse.fact_orders;
-- Query: Total Revenue
-- Business purpose: Calculate the total net revenue generated across all orders.
SELECT SUM(fact_orders.net_amount) AS total_revenue
FROM warehouse.fact_orders;
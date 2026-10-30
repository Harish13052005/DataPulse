-- Expand hashed dimensional/fact surrogate keys before loading large datasets.
BEGIN;

ALTER TABLE fact_order_items
    DROP CONSTRAINT IF EXISTS fact_order_items_order_key_fkey,
    DROP CONSTRAINT IF EXISTS fact_order_items_product_key_fkey,
    DROP CONSTRAINT IF EXISTS fact_order_items_customer_key_fkey;
ALTER TABLE fact_orders
    DROP CONSTRAINT IF EXISTS fact_orders_customer_key_fkey;

ALTER TABLE dim_customers
    ALTER COLUMN customer_key TYPE BIGINT;
ALTER TABLE dim_products
    ALTER COLUMN product_key TYPE BIGINT;
ALTER TABLE fact_orders
    ALTER COLUMN order_key TYPE BIGINT,
    ALTER COLUMN customer_key TYPE BIGINT;
ALTER TABLE fact_order_items
    ALTER COLUMN order_item_key TYPE BIGINT,
    ALTER COLUMN order_key TYPE BIGINT,
    ALTER COLUMN product_key TYPE BIGINT,
    ALTER COLUMN customer_key TYPE BIGINT;

ALTER TABLE fact_orders
    ADD CONSTRAINT fact_orders_customer_key_fkey
    FOREIGN KEY (customer_key) REFERENCES dim_customers(customer_key);
ALTER TABLE fact_order_items
    ADD CONSTRAINT fact_order_items_order_key_fkey
    FOREIGN KEY (order_key) REFERENCES fact_orders(order_key) ON DELETE CASCADE,
    ADD CONSTRAINT fact_order_items_product_key_fkey
    FOREIGN KEY (product_key) REFERENCES dim_products(product_key),
    ADD CONSTRAINT fact_order_items_customer_key_fkey
    FOREIGN KEY (customer_key) REFERENCES dim_customers(customer_key);

COMMIT;

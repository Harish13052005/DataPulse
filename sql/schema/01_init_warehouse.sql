-- ============================================================================
-- DataPulse Intelligent Data Engineering & Analytics Platform
-- Production PostgreSQL 16 DDL Schema Specification (Kimball Star Schema)
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS warehouse;
SET search_path TO warehouse, public;

-- ----------------------------------------------------------------------------
-- Dimension: Customers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_customers (
    customer_key INTEGER PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL UNIQUE,
    first_name VARCHAR(128) NOT NULL,
    last_name VARCHAR(128) NOT NULL,
    full_name VARCHAR(256) NOT NULL,
    email VARCHAR(256) NOT NULL,
    phone VARCHAR(64),
    address VARCHAR(256),
    city VARCHAR(128) NOT NULL,
    state VARCHAR(32) NOT NULL,
    postal_code VARCHAR(32) NOT NULL,
    country VARCHAR(64) NOT NULL DEFAULT 'USA',
    signup_date DATE NOT NULL,
    signup_year INTEGER NOT NULL,
    signup_month INTEGER NOT NULL,
    customer_segment VARCHAR(64) NOT NULL DEFAULT 'Standard',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ingested_at VARCHAR(64) NOT NULL,
    record_hash VARCHAR(64) NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_cust_email ON dim_customers (email);
CREATE INDEX IF NOT EXISTS idx_dim_cust_state ON dim_customers (state);
CREATE INDEX IF NOT EXISTS idx_dim_cust_segment ON dim_customers (customer_segment);
CREATE INDEX IF NOT EXISTS idx_dim_cust_seg_state ON dim_customers (customer_segment, state);

-- ----------------------------------------------------------------------------
-- Dimension: Products
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_products (
    product_key INTEGER PRIMARY KEY,
    product_id VARCHAR(64) NOT NULL UNIQUE,
    product_name VARCHAR(256) NOT NULL,
    category VARCHAR(128) NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    price_tier VARCHAR(64) NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_prod_category ON dim_products (category);
CREATE INDEX IF NOT EXISTS idx_dim_prod_tier ON dim_products (price_tier);

-- ----------------------------------------------------------------------------
-- Dimension: Date
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    day_name VARCHAR(32) NOT NULL,
    month_num INTEGER NOT NULL CHECK (month_num BETWEEN 1 AND 12),
    month_name VARCHAR(32) NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    year INTEGER NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_month_end BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dim_date_year_month ON dim_date (year, month_num);
CREATE INDEX IF NOT EXISTS idx_dim_date_quarter ON dim_date (quarter);

-- ----------------------------------------------------------------------------
-- Fact: Orders
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_orders (
    order_key INTEGER PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL UNIQUE,
    customer_key INTEGER NOT NULL REFERENCES dim_customers(customer_key),
    customer_id VARCHAR(64) NOT NULL,
    order_date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    order_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    status VARCHAR(32) NOT NULL,
    payment_method VARCHAR(64) NOT NULL,
    item_count INTEGER NOT NULL CHECK (item_count >= 1),
    total_quantity INTEGER NOT NULL CHECK (total_quantity >= 1),
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    tax_amount NUMERIC(12, 2) NOT NULL CHECK (tax_amount >= 0),
    shipping_fee NUMERIC(12, 2) NOT NULL CHECK (shipping_fee >= 0),
    discount_amount NUMERIC(12, 2) NOT NULL CHECK (discount_amount >= 0),
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    net_amount NUMERIC(12, 2) NOT NULL CHECK (net_amount >= 0),
    ingested_at VARCHAR(64) NOT NULL,
    record_hash VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_orders_cust ON fact_orders (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_orders_date ON fact_orders (order_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_orders_status ON fact_orders (status);
CREATE INDEX IF NOT EXISTS idx_fact_orders_status_date ON fact_orders (status, order_date_key);

-- ----------------------------------------------------------------------------
-- Fact: Order Items
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_order_items (
    order_item_key INTEGER PRIMARY KEY,
    order_key INTEGER NOT NULL REFERENCES fact_orders(order_key) ON DELETE CASCADE,
    order_id VARCHAR(64) NOT NULL,
    product_key INTEGER NOT NULL REFERENCES dim_products(product_key),
    product_id VARCHAR(64) NOT NULL,
    customer_key INTEGER NOT NULL REFERENCES dim_customers(customer_key),
    order_date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    line_total NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0),
    discount_allocated NUMERIC(12, 2) NOT NULL DEFAULT 0.0 CHECK (discount_allocated >= 0)
);

CREATE INDEX IF NOT EXISTS idx_fact_items_order ON fact_order_items (order_key);
CREATE INDEX IF NOT EXISTS idx_fact_items_prod ON fact_order_items (product_key);
CREATE INDEX IF NOT EXISTS idx_fact_items_cust ON fact_order_items (customer_key);

-- ----------------------------------------------------------------------------
-- Operational Audit: Pipeline Runs
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    pipeline_name VARCHAR(128) NOT NULL,
    start_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    end_time TIMESTAMP WITHOUT TIME ZONE,
    duration_seconds NUMERIC(10, 3),
    status VARCHAR(32) NOT NULL,
    records_ingested INTEGER NOT NULL DEFAULT 0,
    valid_records_loaded INTEGER NOT NULL DEFAULT 0,
    quarantined_records INTEGER NOT NULL DEFAULT 0,
    details_json TEXT
);

-- ----------------------------------------------------------------------------
-- Operational Audit: Quarantine Records
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quarantine_records (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64),
    record_id VARCHAR(64) NOT NULL,
    source_system VARCHAR(64) NOT NULL,
    error_type VARCHAR(64) NOT NULL,
    rule_code VARCHAR(64) NOT NULL,
    field_name VARCHAR(128),
    error_message TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    quarantined_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quarantine_run ON quarantine_records (run_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_rule ON quarantine_records (rule_code);
CREATE INDEX IF NOT EXISTS idx_quarantine_source ON quarantine_records (source_system);

# DataPulse Data Model & Dimensional Warehouse Specification

## 1. Operational Source Schemas

### Source 1: Customer Profiles (CSV)

| Field Name | Source Data Type | Nullable | Description / Business Meaning | Sample Value |
|:---|:---|:---|:---|:---|
| `customer_id` | String | No | Unique natural customer identifier | `"CUST-1001"` |
| `first_name` | String | No | Customer's first given name | `"Alice"` |
| `last_name` | String | No | Customer's family surname | `"Walker"` |
| `email` | String | No | Primary contact email address | `"alice.walker@example.com"` |
| `phone` | String | Yes | E.164 or formatted telephone number | `"+1-555-019-2834"` |
| `address` | String | Yes | Street delivery address | `"123 Innovation Way"` |
| `city` | String | No | City of residence | `"Austin"` |
| `state` | String (2) | No | Two-letter US state abbreviation | `"TX"` |
| `postal_code` | String | No | Postal ZIP code | `"78701"` |
| `country` | String | No | Country of residence (default: USA) | `"USA"` |
| `signup_date` | Date (YYYY-MM-DD)| No | Account registration date | `"2023-04-15"` |
| `customer_segment`| String | No | Account tier: Standard, Premium, VIP | `"Premium"` |
| `is_active` | Boolean | No | Account status flag | `True` |

---

### Source 2: Orders & Transactions (REST API Payload)

**Endpoint:** `GET /api/v1/orders`

```json
{
  "order_id": "ORD-5001",
  "customer_id": "CUST-1001",
  "order_timestamp": "2023-11-20T14:30:00Z",
  "status": "COMPLETED",
  "payment_method": "CREDIT_CARD",
  "subtotal": 249.98,
  "tax_amount": 20.00,
  "shipping_fee": 9.99,
  "discount_amount": 10.00,
  "total_amount": 269.97,
  "items": [
    {
      "item_id": "ITEM-00001",
      "product_id": "PROD-001",
      "product_name": "Pro Wireless Headphones",
      "category": "Electronics",
      "quantity": 1,
      "unit_price": 199.99,
      "line_total": 199.99
    },
    {
      "item_id": "ITEM-00002",
      "product_id": "PROD-006",
      "product_name": "Precision Optical Mouse",
      "category": "Peripherals",
      "quantity": 1,
      "unit_price": 49.99,
      "line_total": 49.99
    }
  ]
}
```

---

## 2. Kimball Star Schema Specification

### Fact Table Grain Definitions:
- **`fact_orders` Grain:** Exactly **one row per customer transaction / order header**. Represents order-level financial aggregates, lifecycle status, payment method, and summary item counts.
- **`fact_order_items` Grain:** Exactly **one row per individual product line item purchased within an order**. Captures item-level quantities, unit prices, extended line amounts, and allocated order-level discounts.

### Surrogate Key Strategy:
- **Technique:** Deterministic positive 32-bit integers derived from SHA-256 digests of natural entity prefixes and IDs:  
  `int.from_bytes(hashlib.sha256(f"{prefix}:{natural_id}".encode()).digest()[:4], "big") % 2147483647`
- **Benefits:**
  1. Decouples the analytical warehouse from operational OLTP natural key changes.
  2. Ensures identical natural keys produce identical surrogate keys across rebuilds without centralized sequence locking.
  3. Fits standard 4-byte indexed integer columns across PostgreSQL and SQLite.

---

## 3. Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    dim_customers ||--o{ fact_orders : "places (1:N)"
    dim_date ||--o{ fact_orders : "ordered_on (1:N)"
    fact_orders ||--|{ fact_order_items : "contains (1:N)"
    dim_products ||--o{ fact_order_items : "line_product (1:N)"
    dim_customers ||--o{ fact_order_items : "purchased_by (1:N)"
    dim_date ||--o{ fact_order_items : "line_date (1:N)"

    dim_customers {
        int customer_key PK "Surrogate Key"
        varchar customer_id UK "Natural ID (CUST-xxxx)"
        varchar first_name "Cleaned First Name"
        varchar last_name "Cleaned Last Name"
        varchar full_name "First + Last Name"
        varchar email "RFC 5322 Email"
        varchar phone "Contact Phone"
        varchar address "Street Address"
        varchar city "City"
        varchar state "2-letter State Code"
        varchar postal_code "Postal ZIP"
        varchar country "Country (USA)"
        date signup_date "Registration Date"
        int signup_year "Cohort Year"
        int signup_month "Cohort Month"
        varchar customer_segment "Standard / Premium / VIP"
        boolean is_active "Active Flag"
        varchar record_hash "SHA-256 Change Detection"
        timestamp updated_at "Last Warehouse Update"
    }

    dim_products {
        int product_key PK "Surrogate Key"
        varchar product_id UK "Natural ID (PROD-xxx)"
        varchar product_name "Catalog Name"
        varchar category "Electronics, Furniture, etc."
        float unit_price "Standard Retail Price"
        varchar price_tier "Budget/Standard/Premium/Luxury"
        timestamp updated_at "Last Warehouse Update"
    }

    dim_date {
        int date_key PK "Date Key (YYYYMMDD)"
        date full_date UK "Calendar Date"
        int day_of_month "Day (1-31)"
        int day_of_week "ISO Day of Week (1-7)"
        varchar day_name "Monday..Sunday"
        int month_num "Month (1-12)"
        varchar month_name "January..December"
        int quarter "Quarter (1-4)"
        int year "Calendar Year"
        boolean is_weekend "Weekend Flag"
        boolean is_month_end "Month End Flag"
    }

    fact_orders {
        int order_key PK "Surrogate Key"
        varchar order_id UK "Natural Order ID (ORD-xxxx)"
        int customer_key FK "References dim_customers"
        varchar customer_id "Natural Customer ID"
        int order_date_key FK "References dim_date"
        timestamp order_timestamp "UTC Order Datetime"
        varchar status "COMPLETED, PENDING, CANCELLED, REFUNDED"
        varchar payment_method "Credit Card, PayPal, etc."
        int item_count "Distinct Line Item Count"
        int total_quantity "Total Units Sold"
        float subtotal "Gross Line Item Sum"
        float tax_amount "Taxes Collected"
        float shipping_fee "Shipping Fee Charged"
        float discount_amount "Discounts Applied"
        float total_amount "Total Billed Amount"
        float net_amount "Net Merchandise Revenue (Subtotal - Discount)"
        varchar record_hash "SHA-256 Digest"
    }

    fact_order_items {
        int order_item_key PK "Surrogate Key"
        int order_key FK "References fact_orders (Cascade)"
        varchar order_id "Natural Order ID"
        int product_key FK "References dim_products"
        varchar product_id "Natural Product ID"
        int customer_key FK "References dim_customers"
        int order_date_key FK "References dim_date"
        int quantity "Units Purchased (>0)"
        float unit_price "Unit Selling Price (>0)"
        float line_total "quantity * unit_price"
        float discount_allocated "Proportional Discount Share"
    }

    pipeline_runs {
        varchar run_id PK "Unique Run Slug"
        varchar pipeline_name "Pipeline Name"
        timestamp start_time "Run Start UTC"
        timestamp end_time "Run End UTC"
        float duration_seconds "Run Duration (s)"
        varchar status "SUCCESS / FAILED / PARTIAL"
        int records_ingested "Total Records Ingested"
        int valid_records_loaded "Valid Records Loaded"
        int quarantined_records "Quarantined Count"
        text details_json "Phase Timers & Throughput"
    }

    quarantine_records {
        int id PK "Serial Sequence"
        varchar run_id "Associated Pipeline Run ID"
        varchar record_id "Rejected Natural ID"
        varchar source_system "CSV_CUSTOMERS / REST_API_ORDERS"
        varchar error_type "SCHEMA_VALIDATION / BUSINESS_RULE"
        varchar rule_code "BR_CUST_001, BR_REF_001, etc."
        varchar field_name "Specific Offending Field"
        text error_message "Diagnostic Description"
        text raw_payload "Complete Unaltered Raw JSON"
        timestamp quarantined_at "UTC Rejection Timestamp"
    }
```

---

## 4. Column Definitions, Constraints & Indexes

### Indices & Performance Optimization:
1. **`dim_customers`:**
   - Unique Index: `customer_id`
   - B-Tree Index: `email`
   - B-Tree Index: `state`
   - Composite Index: `(customer_segment, state)`
2. **`dim_products`:**
   - Unique Index: `product_id`
   - B-Tree Index: `category`
3. **`dim_date`:**
   - Unique Index: `full_date`
   - Composite Index: `(year, month_num)`
4. **`fact_orders`:**
   - Unique Index: `order_id`
   - Foreign Key Index: `customer_key`
   - Foreign Key Index: `order_date_key`
   - Composite Index: `(status, order_date_key)`
5. **`fact_order_items`:**
   - Foreign Key Index: `order_key`
   - Foreign Key Index: `product_key`
   - Foreign Key Index: `customer_key`
6. **`quarantine_records`:**
   - B-Tree Index: `rule_code`
   - B-Tree Index: `run_id`
   - B-Tree Index: `source_system`

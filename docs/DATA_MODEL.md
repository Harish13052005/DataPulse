# DataPulse Data Model

The current field-level dictionary and SQLAlchemy types are maintained in
[`DATA_DICTIONARY.md`](DATA_DICTIONARY.md). The diagram below summarizes the
warehouse grains and relationships.

```mermaid
erDiagram
    dim_customers ||--o{ fact_orders : customer_key
    dim_date ||--o{ fact_orders : order_date_key
    fact_orders ||--|{ fact_order_items : order_key
    dim_products ||--o{ fact_order_items : product_key
    dim_customers ||--o{ fact_order_items : customer_key
    dim_date ||--o{ fact_order_items : order_date_key

    dim_customers {
        bigint customer_key PK
        string customer_id UK
        string first_name
        string last_name
        string email
        string customer_segment
    }
    dim_products {
        bigint product_key PK
        string product_id UK
        string product_name
        string category
        float unit_price
    }
    dim_date {
        int date_key PK
        date full_date UK
        int day_of_week
        int month_num
        int quarter
        int year
    }
    fact_orders {
        bigint order_key PK
        string order_id UK
        bigint customer_key FK
        int order_date_key FK
        string status
        float subtotal
        float discount_amount
        float net_amount
    }
    fact_order_items {
        bigint order_item_key PK
        bigint order_key FK
        bigint product_key FK
        bigint customer_key FK
        int order_date_key FK
        int quantity
        float line_total
    }
```

## Fact grains

- `fact_orders`: one row per source order header.
- `fact_order_items`: one row per product line within an order.
- `dim_customers` and `dim_products`: one row per natural entity identifier.
- `dim_date`: one row per calendar date with an integer `YYYYMMDD` key.
- `pipeline_runs` and `quarantine_records` are operational/audit tables and are
  not part of the sales star schema.

Customer, product, order, and order-line surrogate keys use deterministic
positive 63-bit hashes. Earlier 32-bit keys collided in the 50,000-customer
benchmark input. Existing PostgreSQL databases must be upgraded with
[`../sql/migrations/02_expand_surrogate_keys_to_bigint.sql`](../sql/migrations/02_expand_surrogate_keys_to_bigint.sql)
before loading the new key format. Hash collisions remain theoretically
possible, so primary-key constraints remain important.

See the dictionary for field semantics, nullability, API payloads, and response
contracts.

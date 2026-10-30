# DataPulse Data Dictionary

This document describes the current ingestion payloads, warehouse models,
application API, mock source API, and relevant configuration. Database
definitions in `app/warehouse/models.py` and Pydantic definitions in
`app/validation/schemas.py` are authoritative when details differ.

## Conventions

- `customer_id`, `order_id`, `product_id`, and `item_id` are source natural IDs.
- `*_key` fields are warehouse surrogate/date keys.
- Timestamps are accepted as ISO-8601 strings; generated pipeline timestamps
  use UTC.
- Currency values are treated as USD in the application API and dashboard.
- Ingestion metadata fields begin with `_` and are attached by ingestors; they
  are not all persisted as separate warehouse columns.

## Customer CSV source

Source file default: `data/raw/customers.csv`.

| Field | Type | Required | Meaning / validation |
|---|---|---:|---|
| `customer_id` | string | Yes | Natural customer ID, minimum length 3 |
| `first_name` | string | Yes | Non-empty given name |
| `last_name` | string | Yes | Non-empty surname |
| `email` | string | Yes | Validated with a simple email syntax pattern; stored lowercase |
| `phone` | string or null | No | Optional phone |
| `address` | string or null | No | Optional street address |
| `city` | string | Yes | Non-empty city |
| `state` | string | Yes | Two characters per schema |
| `postal_code` | string | Yes | Minimum length 3 |
| `country` | string | No | Defaults to `USA` |
| `signup_date` | string (`YYYY-MM-DD`) | Yes | Parsed as a calendar date; future dates rejected |
| `customer_segment` | string | No | Defaults to `Standard`; batch validator allows Standard, Premium, VIP |
| `is_active` | boolean | No | Defaults to `true` |

Customer ingestor metadata:

| Field | Meaning |
|---|---|
| `_source_system` | `CSV_CUSTOMERS` |
| `_source_file` | Input file basename |
| `_source_row_num` | Data-row number |
| `_ingested_at` | UTC ingestion timestamp |
| `_record_hash` | SHA-256 hash of normalized row values |
| `_raw_payload` | JSON serialization of source row |

## Mock order source API payload

The mock source API returns a paginated envelope with `page`, `page_size`,
`total_records`, `total_pages`, and `data`. Each `data` element is an order:

| Field | Type | Required | Meaning / validation |
|---|---|---:|---|
| `order_id` | string | Yes | Natural order ID, minimum length 3 |
| `customer_id` | string | Yes | Must match a customer accepted for the current pipeline batch |
| `order_timestamp` | ISO-8601 string | Yes | Order event timestamp |
| `status` | string | Yes | `COMPLETED`, `PENDING`, `CANCELLED`, or `REFUNDED` |
| `payment_method` | string | Yes | Non-empty payment method |
| `subtotal` | number | Yes | Non-negative merchandise subtotal |
| `tax_amount` | number | Yes | Non-negative tax |
| `shipping_fee` | number | Yes | Non-negative shipping |
| `discount_amount` | number | No | Non-negative; batch validator rejects values above 100 |
| `total_amount` | number | Yes | Non-negative billed amount |
| `items` | array | Yes | At least one line item |

Order line item:

| Field | Type | Required | Meaning / validation |
|---|---|---:|---|
| `item_id` | string | Yes | Natural order-line identifier |
| `product_id` | string | Yes | Must exist in the configured synthetic catalog in batch validation |
| `product_name` | string | Yes | Product display name |
| `category` | string | Yes | Product category |
| `quantity` | integer | Yes | Greater than zero |
| `unit_price` | number | Yes | Greater than zero |
| `line_total` | number | Yes | Non-negative extended line amount |

Order ingestion metadata includes `_source_system` (`REST_API_ORDERS`),
`_source_page`, `_source_row_num`, `_ingested_at`, `_record_hash`, and
`_raw_payload`.

## Warehouse tables

### `dim_customers`

Grain: one customer per natural `customer_id`.

| Column | SQLAlchemy type | Nullability / key | Description |
|---|---|---|---|
| `customer_key` | BigInteger | PK | Deterministic positive 63-bit surrogate key |
| `customer_id` | String(64) | Unique, not null | Source natural key |
| `first_name` | String(128) | Not null | Cleaned given name |
| `last_name` | String(128) | Not null | Cleaned surname |
| `full_name` | String(256) | Not null | Display name |
| `email` | String(256) | Not null | Normalized email |
| `phone` | String(64) | Nullable | Phone |
| `address` | String(256) | Nullable | Address |
| `city` | String(128) | Not null | City |
| `state` | String(32) | Not null | State |
| `postal_code` | String(32) | Not null | Postal code |
| `country` | String(64) | Not null | Country, default `USA` |
| `signup_date` | Date | Not null | Signup date |
| `signup_year` | Integer | Not null | Derived signup year |
| `signup_month` | Integer | Not null | Derived signup month |
| `customer_segment` | String(64) | Not null | Customer tier |
| `is_active` | Boolean | Not null | Account flag |
| `ingested_at` | String(64) | Not null | Source ingestion timestamp |
| `record_hash` | String(64) | Not null | Source record digest |
| `updated_at` | DateTime | Not null | Warehouse update timestamp |

### `dim_products`

Grain: one catalog product per natural `product_id`.

| Column | SQLAlchemy type | Nullability / key | Description |
|---|---|---|---|
| `product_key` | BigInteger | PK | Deterministic positive 63-bit surrogate key |
| `product_id` | String(64) | Unique, not null | Product natural key |
| `product_name` | String(256) | Not null | Product name |
| `category` | String(128) | Not null | Catalog category |
| `unit_price` | Float | Not null | Catalog unit price |
| `price_tier` | String(64) | Not null | Derived Budget/Standard/Premium/Luxury band |
| `updated_at` | DateTime | Not null | Warehouse update timestamp |

### `dim_date`

Grain: one calendar date per `full_date`. `date_key` is integer `YYYYMMDD`.

| Column | SQLAlchemy type | Nullability / key | Description |
|---|---|---|---|
| `date_key` | Integer | PK | Date key `YYYYMMDD` |
| `full_date` | Date | Unique, not null | Calendar date |
| `day_of_month` | Integer | Not null | Day number |
| `day_of_week` | Integer | Not null | ISO weekday number, Monday=1 |
| `day_name` | String(32) | Not null | Weekday label |
| `month_num` | Integer | Not null | Month number |
| `month_name` | String(32) | Not null | Month label |
| `quarter` | Integer | Not null | Calendar quarter |
| `year` | Integer | Not null | Calendar year |
| `is_weekend` | Boolean | Not null | Weekend flag |
| `is_month_end` | Boolean | Not null | Last day of month flag |

### `fact_orders`

Grain: one order header per natural `order_id`.

| Column | SQLAlchemy type | Nullability / key | Description |
|---|---|---|---|
| `order_key` | BigInteger | PK | Deterministic positive 63-bit surrogate |
| `order_id` | String(64) | Unique, not null | Source order ID |
| `customer_key` | BigInteger | FK, not null | `dim_customers.customer_key` |
| `customer_id` | String(64) | Not null | Source customer ID for traceability |
| `order_date_key` | Integer | FK, not null | `dim_date.date_key` |
| `order_timestamp` | DateTime | Not null | Parsed order timestamp |
| `status` | String(32) | Not null | Order lifecycle state |
| `payment_method` | String(64) | Not null | Payment method |
| `item_count` | Integer | Not null | Number of lines |
| `total_quantity` | Integer | Not null | Sum of item quantities |
| `subtotal` | Float | Not null | Merchandise subtotal |
| `tax_amount` | Float | Not null | Tax |
| `shipping_fee` | Float | Not null | Shipping |
| `discount_amount` | Float | Not null | Discount amount |
| `total_amount` | Float | Not null | Source order amount |
| `net_amount` | Float | Not null | `subtotal - discount_amount` |
| `ingested_at` | String(64) | Not null | Ingestion timestamp |
| `record_hash` | String(64) | Not null | Source record digest |

### `fact_order_items`

Grain: one product line per order.

| Column | SQLAlchemy type | Nullability / key | Description |
|---|---|---|---|
| `order_item_key` | BigInteger | PK | Deterministic positive 63-bit line key |
| `order_key` | BigInteger | FK, not null | `fact_orders.order_key` |
| `order_id` | String(64) | Not null | Source order ID |
| `product_key` | BigInteger | FK, not null | `dim_products.product_key` |
| `product_id` | String(64) | Not null | Source product ID |
| `customer_key` | BigInteger | FK, not null | `dim_customers.customer_key` |
| `order_date_key` | Integer | FK, not null | `dim_date.date_key` |
| `quantity` | Integer | Not null | Units purchased |
| `unit_price` | Float | Not null | Price per unit |
| `line_total` | Float | Not null | Extended line value |
| `discount_allocated` | Float | Not null | Line-level allocated discount |

### Operational tables

| Table | Columns |
|---|---|
| `pipeline_runs` | `run_id` (PK), `pipeline_name`, `start_time`, `end_time`, `duration_seconds`, `status`, `records_ingested`, `valid_records_loaded`, `quarantined_records`, `details_json` |
| `quarantine_records` | `id` (PK), `run_id`, `record_id`, `source_system`, `error_type`, `rule_code`, `field_name`, `error_message`, `raw_payload`, `quarantined_at` |

## Application API

Base URL when running locally: `http://127.0.0.1:8001`. Responses are Pydantic
models; paginated responses use `page`, `page_size`, `total_records`,
`total_pages`, and `data`.

| Method and path | Purpose | Query/body | Important responses |
|---|---|---|---|
| `GET /health` | API and DB connectivity | None | `200` healthy, database connected; DB errors use `503` |
| `GET /api/v1/pipeline/runs` | List pipeline run audits | `page` (>=1), `page_size` (1-100) | Paginated run response |
| `GET /api/v1/pipeline/runs/{run_id}` | Get run detail | Path `run_id` | `404` if absent |
| `POST /api/v1/pipeline/run` | Execute pipeline | JSON `{"force_mock_api_client": true}`; defaults true | `201` with result, `500` on pipeline failure |
| `GET /api/v1/quality/summary` | Rejection totals grouped by rule and source | None | `total_rejected_records`, `by_rule`, `by_source` |
| `GET /api/v1/quality/rejected-records` | Browse rejected rows | `page`, `page_size` (1-100), optional `run_id` | Paginated quarantine records |
| `GET /api/v1/analytics/revenue` | Revenue aggregate | Optional `start_date`, `end_date` | USD order counts, gross/net totals, AOV; reversed date range `422` |
| `GET /api/v1/analytics/top-products` | Rank completed-order products | `page`, `page_size` (1-100) | Paginated product metrics |
| `GET /api/v1/analytics/monthly-trends` | Monthly order and revenue metrics | `page`, `page_size` (1-100) | Paginated month metrics |

FastAPI validation errors, including invalid pagination, return `422`. OpenAPI
and interactive Swagger UI are served at `/openapi.json` and `/docs`.

## Mock source API

Base URL: `http://127.0.0.1:8000`.

| Method and path | Purpose | Parameters |
|---|---|---|
| `GET /health` | Source service health and catalog/order counts | None |
| `GET /api/v1/products` | Synthetic product catalog | None |
| `GET /api/v1/orders` | Paginated synthetic orders | `page` >=1; `page_size` 1-500; optional `status`, `customer_id` |
| `GET /api/v1/orders/{order_id}` | Look up a single order | Path natural ID; `404` if absent |

This is the mock **ingestion source**, not the warehouse application API.

## Configuration variables

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `DataPulse` | Display name |
| `APP_ENV` | `development` | Environment label |
| `DEBUG` | `false` | Debug flag |
| `LOG_LEVEL` | `INFO` | Logging level |
| `RANDOM_SEED` | `42` | Synthetic data seed |
| `DATABASE_URL` | Project-root SQLite file | SQLAlchemy database URL |
| `DB_ECHO` | `false` | SQL logging |
| `POSTGRES_DB` | `datapulse_dw` | Compose PostgreSQL database |
| `POSTGRES_USER` | `datapulse` | Compose PostgreSQL user |
| `POSTGRES_PASSWORD` | Example local value | Compose PostgreSQL password; replace for shared deployments |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host setting |
| `POSTGRES_PORT` | `5432` | PostgreSQL port setting |
| `API_HOST` | `127.0.0.1` | Local service bind host |
| `API_PORT` | `8000` | Mock source port |
| `APP_API_PORT` | `8001` | Application API port |
| `API_BASE_URL` | `http://127.0.0.1:8000` | HTTP source base URL |
| `APP_API_BASE_URL` | `http://127.0.0.1:8001` | Dashboard application API URL |
| `API_TIMEOUT_SECONDS` | `10.0` | HTTP source timeout |
| `API_PAGE_SIZE` | `50` | Default source page size |
| `BATCH_SIZE` | `500` | Configured batch size |
| `RETRY_ATTEMPTS` | `3` | HTTP retries |
| `RETRY_BACKOFF_FACTOR` | `0.5` | Exponential backoff base |
| `INJECT_DIRTY_DATA_RATIO` | `0.08` | Synthetic invalid-data ratio |

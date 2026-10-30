# DataPulse Architectural & Technical Decision Records (ADRs)

## ADR-01: Dual-Dialect Database Support (PostgreSQL 16 & SQLite Fallback)

### Context:
Technical recruiters and evaluation reviewers execute candidate projects across varied environments. While PostgreSQL is the enterprise standard for dimensional warehouses, requiring a running Docker daemon or local Postgres server creates friction if the evaluator's machine lacks Docker permissions or local Postgres services.

### Decision:
Implement an abstract database connection layer via **SQLAlchemy 2.0** supporting:
1. **Production Mode:** PostgreSQL 16 via Docker Compose (`postgresql+psycopg2://...`) with dedicated DDL scripts, constraints, and connection pooling.
2. **Local Evaluation Mode:** Zero-dependency SQLite (`sqlite:///datapulse_warehouse.db`) with automatic WAL mode (`PRAGMA journal_mode=WAL`) and foreign key enforcement (`PRAGMA foreign_keys=ON`).
Both dialects use the exact same declarative ORM models and ANSI-compliant SQL analytical queries.

### Consequences:
- **Positive:** Project evaluates with zero friction in 100% of candidate test environments while remaining 100% cloud/Docker-deployable.
- **Negative:** Advanced Postgres-only features (e.g. BRIN indexes or JSONB operators) must be avoided in favor of standard relational schemas.

---

## ADR-02: Pydantic V2 & Declarative Rule Engine over Pandera

### Context:
Data validation can be handled via dataframe-level tools (e.g. Pandera) or record-level typed schemas (e.g. Pydantic). Because Source 2 (Orders REST API) arrives as nested hierarchical JSON (`orders -> items[]`), flat tabular dataframe validation struggles with deeply nested arrays and per-item financial consistency checks.

### Decision:
Use **Pydantic V2** (`BaseModel`, `@field_validator`) for syntactic and type-level validation, paired with a custom **`BusinessRuleValidator`** engine that enforces cross-entity business rules:
- Hierarchical validation: Validates nested items within orders directly in memory with microsecond latency.
- Cross-entity referential integrity (`BR_REF_001`): Orders are checked against the set of valid customer IDs before warehouse loading.
- Detailed error attribution: Captures exact field locations, error types, and rule codes for quarantine logs.

### Consequences:
- **Positive:** Unmatched speed (Pydantic V2 core written in Rust), clean type safety, and rich nested schema support.
- **Negative:** Requires dictionary serialization when passing to Pandas, which is encapsulated cleanly inside ingestion wrappers.

---

## ADR-03: Non-Destructive Quarantine Pattern

### Context:
Traditional ETL pipelines often silently discard invalid records (`DROP ROW` or filter out `NaN` values), causing data loss, untracked operational issues, and unexplainable discrepancies between source systems and analytical warehouses.

### Decision:
Implement a **Strict Non-Destructive Quarantine Pattern**:
1. Zero records are silently dropped.
2. Every rejected record is intercepted by `QuarantineManager`.
3. The unaltered raw payload is serialized and saved along with the failure reason, rule code, and ingestion timestamp.
4. Quarantined records are persisted to disk (`data/quarantine/*.csv` and `*.jsonl`) and loaded into the `quarantine_records` database table.
5. The Streamlit dashboard includes a dedicated Quarantine Inspector enabling engineers to inspect rejected raw JSON payloads with one click.

---

## ADR-04: Natural Key Hash Comparison for Pipeline Idempotency

### Context:
In production, pipelines frequently execute multiple times due to retries, schedule overlaps, or backfilling. A non-idempotent pipeline causes duplicate counting, inflated metrics, and corrupted dimensions.

### Decision:
Implement **Hash-Based Change Detection and Natural Key Upserts**:
1. During ingestion, a deterministic SHA-256 digest is generated from the normalized raw record dictionary.
2. In the warehouse loader (`WarehouseLoader`):
   - Query existing rows by natural key (`customer_id`, `order_id`, `product_id`).
   - If the natural key does not exist: execute `INSERT`.
   - If the natural key exists and the incoming `record_hash == existing.record_hash`: `SKIP` (mark unchanged).
   - If the natural key exists and `record_hash != existing.record_hash`: execute `UPDATE` of mutable attributes and update `updated_at`.
3. Fact order updates atomically replace associated line items in the same transaction.

### Consequences:
- Re-running the pipeline on identical input data results in **0 duplicate rows** and 0 updated rows. Verified by automated tests.

---

## ADR-05: FastAPI Mock REST API with In-Process TestClient Fallback

### Context:
Source 2 requires order ingestion from a locally hosted REST API. Running a secondary background terminal process (`uvicorn`) during automated unit tests (`pytest`) or automated evaluation can lead to port conflicts, timing issues, or CI/CD test flakes.

### Decision:
Build the mock server using **FastAPI**, and equip `OrdersAPIIngestor` with a dual transport strategy:
1. When running live, connect via standard HTTP (`httpx.Client(base_url="http://localhost:8000")`) with exponential backoff retries.
2. If the HTTP server is unreachable or when running within automated tests, seamlessly fall back to an in-process ASGI client (`TestClient(app)`).

### Consequences:
- Unit tests and automated evaluations run immediately with zero external dependencies and zero port-binding failures, while the standalone FastAPI server remains fully accessible for external inspection.

---

## ADR-06: Analytical SQL Query Design (RFM, MoM Revenue, CLV)

### Context:
Analytical dashboards require business metrics computed efficiently directly within the warehouse engine rather than heavy in-memory Python loops.

### Decision:
Design optimized SQL queries using CTEs (Common Table Expressions) and Window Functions:
1. **RFM Segmentation:**
   - Recency: Difference in days between reference date and customer's latest order.
   - Frequency: Count of distinct completed orders.
   - Monetary: Total net amount spend.
   - Segments: Champions, Loyal Customers, Potential Loyalists, New Customers, At Risk, Needs Attention.
2. **Monthly Revenue & MoM Growth:**
   - Aggregates completed vs refunded orders, gross revenue, discounts, and net revenue grouped by year and month.
   - Computes MoM growth rate using `LAG(net_revenue) OVER (ORDER BY year, month_num)`.
3. **Customer Lifetime Value (CLV):**
   - Aggregated net spend per customer within each demographic tier (Standard, Premium, VIP).
4. **Top Products:**
   - Aggregates `fact_order_items` joined with `dim_products` and filters by `fact_orders.status = 'COMPLETED'`.

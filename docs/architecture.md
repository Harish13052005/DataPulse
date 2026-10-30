# DataPulse Platform Architecture Specification

## 1. High-Level Architecture Overview

DataPulse is an idempotent, decoupled ELT data engineering platform. It ingests customer demographic batches and paginated transactional order streams, validates every record against structural and domain rules, stages invalid records in an auditable quarantine repository, transforms clean data into a Kimball Star Schema warehouse, and powers executive business intelligence.

```mermaid
flowchart TD
    subgraph Sources["Operational Data Sources"]
        S1["Source 1: Customers CSV File<br/>(File Ingestion)"]
        S2["Source 2: Orders REST API<br/>(FastAPI HTTP / In-Process ASGI)"]
    end

    subgraph Ingestion["Ingestion Layer & Audit Metadata"]
        I1["CustomerCSVIngestor<br/>• File streaming / chunking<br/>• SHA-256 Record Hash<br/>• Ingestion Timestamp"]
        I2["OrdersAPIIngestor<br/>• Pagination Engine (page_size=50)<br/>• Exponential Backoff Retries<br/>• TestClient Zero-Downtime Fallback"]
    end

    subgraph Quality["Validation & Quarantine Engine"]
        V1["Pydantic V2 Structural Schema Validation<br/>(CustomerRawSchema, OrderRawSchema)"]
        V2["Domain Business Rules Engine<br/>(BR_CUST_001..004, BR_ORD_001..005)"]
        V3["Cross-Entity Referential Integrity Check<br/>(BR_REF_001: Order Customer in Valid Customers)"]
        QM["Quarantine Manager<br/>• data/quarantine/*.csv<br/>• data/quarantine/*.jsonl<br/>• DB: quarantine_records table"]
    end

    subgraph Transformation["Transformation & Dimensional Modeling"]
        T1["DataCleaner<br/>(Trimming, Title Casing, UTC ISO normalization)"]
        T2["Surrogate Key Generator<br/>(Deterministic 32-bit Integer Hashing)"]
        T3["Calendar Date Dimension Engine<br/>(365+ Days, 11 Temporal Attributes)"]
        T4["Fact & Dimension Entity Mapper"]
    end

    subgraph Warehouse["Kimball Star Schema Data Warehouse"]
        DC["dim_customers"]
        DP["dim_products"]
        DD["dim_date"]
        FO["fact_orders"]
        FI["fact_order_items"]
        PR["pipeline_runs (Audit)"]
        QR["quarantine_records"]
    end

    subgraph Presentation["Analytics & Presentation Layer"]
        AQ["Analytical SQL Engine<br/>(RFM, MoM Revenue, CLV, Category Insights)"]
        REP["Analytics Reporter<br/>(data/reports/*.csv, executive_summary.json)"]
        DASH["Streamlit Interactive Web UI<br/>(Port 8501: 5 Specialized Tabs)"]
    end

    S1 --> I1
    S2 --> I2
    I1 --> V1
    I2 --> V1
    V1 --> V2
    V2 --> V3
    V3 -- Valid Customer & Order Records --> T1
    V3 -- Malformed / Rejected Records --> QM
    QM --> QR
    T1 --> T2 --> T3 --> T4
    T4 --> DC
    T4 --> DP
    T4 --> DD
    T4 --> FO
    T4 --> FI
    T4 --> PR
    DC --> AQ
    DP --> AQ
    DD --> AQ
    FO --> AQ
    FI --> AQ
    AQ --> REP
    AQ --> DASH
    QR --> DASH
    PR --> DASH
```

---

## 2. Ingestion Protocols, Pagination & Retry Resilience

### Source 1: Customers CSV File
- **Protocol:** Local filesystem file stream with UTF-8-sig encoding support (stripping BOM headers).
- **Audit Traceability:** Each row is enriched with:
  - `_source_system`: Literal `"CSV_CUSTOMERS"`
  - `_source_file`: Base filename (e.g. `customers.csv`)
  - `_source_row_num`: Sequential file line number
  - `_ingested_at`: UTC ISO timestamp
  - `_record_hash`: SHA-256 digest of normalized payload
  - `_raw_payload`: Unaltered serialized JSON string

### Source 2: Orders REST API
- **Protocol:** HTTP/1.1 REST (`GET /api/v1/orders`) with query parameters:
  - `page`: 1-based page index
  - `page_size`: default 50 records per page (up to 500)
- **Pagination Strategy:** Deterministic multi-page consumer that reads `total_pages` from the response payload and iterates sequentially until exhaustion or `max_pages` limit.
- **Retry with Exponential Backoff:**
  - Configurable retry attempts (`RETRY_ATTEMPTS=3`).
  - Delay calculation: `delay = backoff_factor * (2 ** (attempt - 1))`.
  - Catches transient network errors, socket timeouts, and HTTP 5xx codes.
- **In-Process ASGI Zero-Downtime Fallback:**
  - If the standalone HTTP server is offline or unreachable during CLI/test execution, `OrdersAPIIngestor` immediately switches to an in-process FastAPI `TestClient(app)` transport without network overhead or port conflicts.

---

## 3. Non-Destructive Error Handling & Quarantine Architecture

```
Raw Record Ingested
       │
       ▼
Pydantic Schema Validation ──(Invalid)──► Collect Syntax Violations
       │ (Valid)                               │
       ▼                                       │
Domain Business Rules       ──(Invalid)──► Collect Semantic Violations
       │ (Valid)                               │
       ▼                                       │
Cross-Entity Integrity Check──(Invalid)──► Collect Referential Violations
       │ (Valid)                               │
       │                                       ▼
       │                          QuarantineManager.record_quarantine()
       │                                       │
       │                                       ├─► Append to in-memory audit log
       │                                       ├─► Persist to data/quarantine/*.csv
       │                                       ├─► Persist to data/quarantine/*.jsonl
       │                                       └─► Stage for DB quarantine_records table
       ▼
Safe for Star Schema Transformation & Loading
```

### Quarantine Invariants:
1. **Never Silently Discard:** Every invalid record must be recorded.
2. **Payload Preservation:** Full unaltered raw input is retained in `raw_payload` for root-cause debugging.
3. **Structured Attribution:** Violations contain `rule_code` (e.g., `BR_CUST_001`), `field_name`, `error_type`, and descriptive message.
4. **Dual Persistence:** Stored both on disk (CSV/JSONL for archival) and in the database warehouse (`quarantine_records` table for dashboard queries).

---

## 4. Idempotency & Upsert Strategy

To ensure that scheduled pipeline executions or manual reruns produce the exact same warehouse state without data duplication:

```mermaid
flowchart TD
    Rec["Incoming Transformed Entity<br/>(Natural Key + Record Hash)"]
    Lookup{"Natural Key<br/>Exists in Table?"}
    Compare{"DB Record Hash ==<br/>Incoming Hash?"}
    Insert["INSERT Entity Row"]
    Update["UPDATE Entity Row Attributes<br/>& set updated_at = NOW()"]
    Skip["SKIP (Unchanged)<br/>Increment unchanged_count"]

    Rec --> Lookup
    Lookup -- No --> Insert
    Lookup -- Yes --> Compare
    Compare -- No (Data Changed) --> Update
    Compare -- Yes (Identical) --> Skip
```

### ACID Transaction Boundary:
All database operations for a pipeline run execute within a single SQLAlchemy transaction (`with get_db_session() as session:`). If any unexpected error occurs, the session is rolled back completely, guaranteeing zero partial states.

---

## 5. Observability, Logging & Pipeline Health Metrics

### Structured Logging:
- Standard format: `[YYYY-MM-DD HH:MM:SS] [LEVEL] [LOGGER_NAME] Message`
- Multi-target output:
  - Console `sys.stdout` for interactive CLI feedback
  - File `logs/datapulse_pipeline.log` for persistent troubleshooting

### Pipeline Execution Auditing (`pipeline_runs` Table):
- `run_id`: Unique run identifier (e.g., `DP-20261030-075101-ce65f4`).
- `pipeline_name`: Literal `"datapulse_ecommerce_pipeline"`.
- `start_time` / `end_time`: UTC timestamps.
- `duration_seconds`: Total runtime in seconds.
- `status`: Execution status (`SUCCESS`, `FAILED`, `PARTIAL`).
- `records_ingested`: Sum of all input records.
- `valid_records_loaded`: Clean dimensional records loaded.
- `quarantined_records`: Count of records routed to quarantine.
- `details_json`: Detailed metrics breakdown including phase timers and throughput (records/second).

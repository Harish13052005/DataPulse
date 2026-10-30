# ⚡ DataPulse – Intelligent Data Engineering & Analytics Platform

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20%7C%20SQLite-336791.svg)](https://www.postgresql.org/)
[![ORM](https://img.shields.io/badge/ORM-SQLAlchemy%202.0-red.svg)](https://www.sqlalchemy.org/)
[![API](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Dashboard](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Validation](https://img.shields.io/badge/Validation-Pydantic%20V2-E92063.svg)](https://pydantic.dev/)
[![Tests](https://img.shields.io/badge/Tests-25%20Passed-brightgreen.svg)](https://docs.pytest.org/)

> **72-Hour Technical Assessment Deliverable**  
> **Role:** Associate AI Forward Deployed Engineer  
> **Candidate Implementation:** Production-Grade E-Commerce Analytics Data Platform

---

## 🌟 Executive Summary

**DataPulse** is an enterprise-grade, idempotent ELT (Extract, Load, Transform) data engineering platform built to ingest, validate, quarantine, transform, model, and analyze high-volume e-commerce transaction data.

The platform addresses two operational data sources:
1. **Source 1 (Batch File):** Customer demographics, registration dates, and segment profiles stored in CSV format.
2. **Source 2 (Streaming/REST API):** High-throughput orders and line item transactions served by a mock REST API (FastAPI) with pagination, filtering, and connection resiliency.

---

## 📁 Project Directory Structure

```
datapulse/
├── app/
│   ├── api/                    # Source 2: Mock Orders REST API (FastAPI) & data generator
│   ├── ingestion/              # Ingestion modules for CSV and REST API with SHA-256 hashing
│   ├── validation/             # Pydantic V2 schemas, business rules, and quarantine router
│   ├── transformation/         # Data cleaner, surrogate keys, date dimension builder
│   ├── warehouse/              # SQLAlchemy connection, ORM models, and idempotent loader
│   ├── monitoring/             # Structured logger, phase timers, and operational metrics
│   ├── analytics/              # Analytical SQL queries (RFM, MoM, CLV) and reports exporter
│   ├── config/                 # Centralized configuration (app/config/settings.py)
│   └── pipeline.py             # Master ELT pipeline orchestrator
├── data/
│   ├── raw/                    # Source 1 raw customers CSV
│   ├── processed/              # Transformed analytical exports (RFM, trends, summary)
│   ├── sample/                 # Sample seed datasets
│   └── quarantine/             # Non-destructive quarantine logs (CSV & JSONL)
├── sql/
│   ├── schema/                 # Production PostgreSQL DDL (01_init_warehouse.sql)
│   └── queries/                # Standalone analytical SQL queries (RFM, MoM, products)
├── tests/
│   ├── unit/                   # Unit test suites (ingestion, validation, transforms, idempotency)
│   ├── integration/            # Integration test suites (E2E pipeline, database ping)
│   ├── fixtures/               # Test data fixtures and mock payloads
│   └── conftest.py             # Pytest configuration and database session fixtures
├── scripts/
│   ├── generate_seed_data.py   # Deterministic seed data generator (seed=42)
│   ├── run_pipeline.py         # Pipeline CLI execution runner
│   ├── benchmark_performance.py# Throughput and SQL latency profiler
│   └── run_all.py              # Master workflow verification script
├── docs/
│   ├── PROJECT_PLAN.md         # Detailed technical plan, stages & dependencies
│   ├── ARCHITECTURE.md         # Complete system architecture and Mermaid diagrams
│   ├── DATA_MODEL.md           # Kimball Star Schema specification & Mermaid ER diagram
│   └── TECHNICAL_DECISIONS.md  # Architectural Decision Records (ADR 01-06)
├── dashboard/
│   └── app.py                  # Interactive 5-tab Streamlit Analytics Dashboard
├── logs/
│   └── datapulse.log           # Rotating structured operational execution log
├── docker/
│   └── init.sql                # PostgreSQL container schema initialization
├── .env.example                # Configuration template (no committed secrets)
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container build specification
├── docker-compose.yml          # PostgreSQL, API, Pipeline, and Dashboard services
├── README.md                   # Complete documentation and evaluation guide
└── main.py                     # Central application entrypoint & health check
```

---

## 🚀 Setup & Execution Guide

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/your-username/datapulse.git
cd datapulse

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Run Application Health Check & Database Ping

```bash
python main.py --health
```
This performs a diagnostic audit:
- Environment & Python runtime validation
- Database connection test and ping latency measurement
- Storage directory structure status
- Ingestion source file availability check

### 3. Master Workflow Verification (One Command)

```bash
python scripts/run_all.py
```
Sequentially runs:
1. Deterministic seed data generation (`seed=42`)
2. Full automated test suite (unit + integration tests)
3. Pipeline execution with idempotent dimensional warehouse loading
4. Analytical reports export to `data/processed/`
5. Performance profiling & SQL query latency benchmarks
6. Application health check audit

### 4. Interactive Services

#### Launch the Streamlit Analytics Dashboard:
```bash
streamlit run dashboard/app.py
```
Open **`http://localhost:8501`** to access:
- **Executive KPIs & Monthly Revenue Trends**
- **RFM Customer Segmentation Matrix**
- **Product Performance & Category Distribution**
- **Data Quality & Real-Time Quarantine Inspector**
- **Live Dimensional Warehouse Explorer**

#### Launch the Mock Orders REST API:
```bash
uvicorn app.api.app:app --reload --port 8000
```
Swagger UI Documentation: **`http://localhost:8000/docs`**

#### Run Production Docker Compose Stack:
```bash
docker compose up --build
```
Includes PostgreSQL 16 (port 5432) with persistent volume storage and health checks, FastAPI REST API (port 8000), DataPulse Pipeline container, and Streamlit Dashboard (port 8501).

---

## 🧪 Automated Testing Suite

```bash
pytest -v
```

All 25 tests pass with a 100% pass rate:
- `tests/unit/test_ingestion.py`: CSV parsing, API pagination, error handling, SHA-256 hashing.
- `tests/unit/test_validation.py`: Pydantic V2 schemas, business rules (`BR_CUST_001..004`, `BR_ORD_001..005`, `BR_REF_001`), quarantine manager.
- `tests/unit/test_transformation.py`: Data cleaner, surrogate keys, date dimension builder, product tiering.
- `tests/unit/test_loader_idempotency.py`: Idempotent loading, duplicate prevention, changed record hash updates.
- `tests/unit/test_analytics.py`: RFM segmentation, monthly trends, top products, category breakdowns.
- `tests/integration/test_pipeline_end_to_end.py`: End-to-end pipeline execution lifecycle.
- `tests/integration/test_database_connectivity.py`: Live database connection verification and ping latency test.

---

## ⚡ Performance Profiling

Run the performance benchmark profiler:
```bash
python scripts/benchmark_performance.py
```

- **Pipeline Throughput:** **~1,250 records / second**
- **Full Pipeline Execution Duration:** **< 1.0 second** (1,250 records ingested, validated, transformed, loaded)
- **Analytical Query Latencies:**
  - Executive KPIs Scorecard: `1.85 ms`
  - RFM Customer Segmentation: `9.58 ms`
  - Monthly Revenue Trends: `3.27 ms`
  - Category Breakdown: `4.56 ms`
  - Top Products Ranking: `6.70 ms`
  - Customer Lifetime Value (CLV): `3.20 ms`

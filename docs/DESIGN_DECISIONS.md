# DataPulse Design Decisions

This document records the main implementation choices and their trade-offs.
These are project design notes, not claims that the current implementation is
production-ready.

## 1. Local-first SQLAlchemy storage

**Decision:** use shared SQLAlchemy ORM models with SQLite as the local default
and PostgreSQL 16 as the Compose database.

**Reasoning:** a new developer can run and test the project without installing a
database server; the PostgreSQL DDL and container stack demonstrate an
alternative relational warehouse.

**Trade-off:** SQLite and PostgreSQL have different concurrency and performance
characteristics. Benchmark results from SQLite must not be generalized to
PostgreSQL.

## 2. Separate source API and warehouse API

**Decision:** use `app.api.mock_app` for synthetic source orders and
`app.api.app` for warehouse operations and analytics.

**Reasoning:** source-system transport and application/warehouse operations are
different interfaces and should not be confused. The application API is
documented in its own Swagger UI.

**Trade-off:** there are two services and two local ports to explain and
configure. The pipeline defaults to an in-process ASGI source transport, so the
source server is not required for the default local run.

## 3. Record schemas with Pydantic

**Decision:** represent customer, order, and line-item payload requirements as
Pydantic models, with business validation layered in Python.

**Reasoning:** source payloads include nested order lines and need readable
field-specific validation failures.

**Trade-off:** validation is currently record-oriented in the main pipeline.
Batch-wide duplicate and schema-drift helpers are present, but not fully wired
into orchestration.

## 4. Quarantine rather than silently dropping invalid inputs

**Decision:** retain rejected payloads and associate them with source and
validation reason metadata.

**Reasoning:** pipeline failures and quality issues need an auditable diagnostic
path.

**Trade-off:** raw payload persistence requires retention, access, and privacy
policies before using sensitive or regulated data. No such lifecycle policy is
implemented in this project.

## 5. Deterministic surrogate keys and wider key types

**Decision:** derive stable positive 63-bit integer keys from SHA-256 hashes of
entity identifiers. Calendar dates use `YYYYMMDD`.

**Reasoning:** stable hashes allow the same business identifier to map to the
same dimensional key across repeated loads without an external sequence
service.

**Trade-off:** hash keys can theoretically collide; the application must still
handle uniqueness constraints. 32-bit keys collided during a 50,000-customer
benchmark input, so warehouse surrogate keys were widened to 63-bit. Existing
PostgreSQL installations require the supplied migration before loading the new
key values.

## 6. Idempotent merge semantics with batched prefetch

**Decision:** compare current and incoming values, then skip unchanged rows,
update changed rows, or insert new rows. Existing primary keys are selected in
batches of up to 500 before row comparison.

**Reasoning:** rerunning an input should not duplicate warehouse entities; the
benchmark showed the previous one-lookup-per-row approach dominated load time.

**Trade-off:** rows are still materialized as Python dictionaries and ORM
objects. The approach reduces lookup round trips but is not a dialect-specific
bulk upsert; different record distributions and databases need separate
measurement.

## 7. Application API response contracts

**Decision:** expose typed Pydantic response models, pagination, explicit
status codes, and FastAPI-generated OpenAPI/Swagger documentation.

**Reasoning:** the dashboard and API users need a clear interface independent of
the mock source payload.

**Trade-off:** the current API has no authentication or authorization, and
pipeline execution is synchronous in the request handler.

## 8. Dashboard reads the warehouse and calls API operations

**Decision:** use direct SQLAlchemy queries for analytical display and the
application API for health and pipeline operations.

**Reasoning:** the dashboard can present database analytics and operational
actions within a single interface.

**Trade-off:** this couples the dashboard to both database connectivity and API
availability. A future deployment could route all dashboard data through the
application API.

## 9. Isolated tests and reproducible benchmark

**Decision:** use per-test temporary SQLite databases and deterministic
fixtures. Benchmark generated datasets in fresh temporary databases.

**Reasoning:** test runs should not alter the developer warehouse, and
performance comparisons should use matching inputs.

**Trade-off:** test and benchmark environments do not represent production
traffic, data skew, Postgres concurrency, or external network delay.

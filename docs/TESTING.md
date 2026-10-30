# DataPulse Testing Guide

## Test strategy

The suite uses Pytest with function-scoped temporary SQLite databases for
database integration tests. SQLite foreign-key enforcement is enabled in the
fixture. Quarantine output is redirected to each test's temporary directory.
The mock order API is exercised in-process; tests do not require a public API,
Docker, or writes to the configured default warehouse.

Run the complete suite from the repository root:

```powershell
python -m pytest -v
```

For a concise result:

```powershell
python -m pytest -q
```

Run a focused area:

```powershell
python -m pytest tests\unit\test_validation.py -v
python -m pytest tests\integration\test_application_api.py -v
python -m pytest tests\integration\test_pipeline_end_to_end.py -v
```

## Coverage map

| Test file | Scope |
|---|---|
| `tests/unit/test_ingestion.py` | CSV parsing, malformed/empty input, response pagination and partial page failure |
| `tests/unit/test_validation.py` | Pydantic schema, null/missing values, date/email checks, duplicates, foreign-key references, discount and quality calculation |
| `tests/unit/test_transformation.py` | Cleaning, surrogate-key determinism and scale, date dimensions, product tiering, order facts |
| `tests/unit/test_loader_idempotency.py` | Insert/update/unchanged behavior, repeated loads, batched SELECT query count |
| `tests/unit/test_analytics.py` | Analytics correctness and empty warehouse behavior |
| `tests/integration/test_database_connectivity.py` | Isolated DB health and failed connection diagnostic |
| `tests/integration/test_database_constraints.py` | Natural-key uniqueness and foreign-key enforcement |
| `tests/integration/test_ingestion_to_warehouse.py` | CSV and local REST-style source ingestion through warehouse rows |
| `tests/integration/test_pipeline_end_to_end.py` | Full run, empty batch, replay, retry, and late historical order |
| `tests/integration/test_application_api.py` | Health, Swagger, pipeline, quality, analytics, pagination and validation |

Fixtures and sample payloads are in `tests/conftest.py` and
`tests/fixtures/sample_data.py`. The `test_engine` fixture creates a temporary
database per test, patches application session/engine references, and drops the
schema at teardown.

## Latest recorded execution

During documentation preparation, the full command `python -m pytest -q`
completed with:

| Passed | Failed | Skipped | Total |
|---:|---:|---:|---:|
| 50 | 0 | 0 | 50 |

This is an observed run, not a guarantee for future code or environments. The
repository summary is [`../test-results/test-execution-report.md`](../test-results/test-execution-report.md).

## Test data safety and scope

- Tests use generated fixtures and isolated `tmp_path` SQLite files.
- The connectivity failure test points to an intentionally unavailable
  temporary path; it does not shut down or alter a real database.
- The source API's module-level store is monkeypatched in tests.
- No tests call a public API.
- These are unit and integration tests; they are not a production-scale load,
  security, or multi-process concurrency test.

## Reproducibility

Run tests from the project root using the installed `requirements.txt`
environment. Tests rely on system-independent SQLite and frozen fixture values;
date validation checks future dates against the current date, so historical
test fixture values should remain in use.

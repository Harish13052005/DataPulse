"""Integration coverage for the warehouse-facing FastAPI application."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.app import app
from app.api.routes import get_db
from app.api import services
from app.warehouse.models import PipelineRun, QuarantineRecord


@pytest.fixture
def api_client(test_engine, test_db_session: Session, seeded_warehouse):
    def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    test_db_session.add(
        PipelineRun(
            run_id="run-test",
            pipeline_name="integration-test",
            start_time=datetime(2026, 1, 1),
            end_time=datetime(2026, 1, 1, 0, 1),
            duration_seconds=60,
            status="SUCCESS",
            records_ingested=10,
            valid_records_loaded=8,
            quarantined_records=2,
        )
    )
    test_db_session.add(
        QuarantineRecord(
            run_id="run-test",
            record_id="bad-1",
            source_system="test",
            error_type="validation",
            rule_code="RULE_1",
            field_name="email",
            error_message="Invalid email",
            raw_payload='{"email":"invalid"}',
            quarantined_at=datetime(2026, 1, 1),
        )
    )
    test_db_session.commit()

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_health_and_swagger_docs(api_client: TestClient):
    health_response = api_client.get("/health")
    docs_response = api_client.get("/docs")

    assert health_response.status_code == 200
    assert health_response.json()["service"] == "datapulse-application-api"
    assert docs_response.status_code == 200
    assert "swagger-ui" in docs_response.text.lower()


def test_pipeline_run_list_detail_and_not_found(api_client: TestClient):
    listing = api_client.get("/api/v1/pipeline/runs?page=1&page_size=1")
    detail = api_client.get("/api/v1/pipeline/runs/run-test")
    missing = api_client.get("/api/v1/pipeline/runs/does-not-exist")

    assert listing.status_code == 200
    assert listing.json()["total_records"] == 1
    assert listing.json()["data"][0]["run_id"] == "run-test"
    assert detail.status_code == 200
    assert detail.json()["status"] == "SUCCESS"
    assert missing.status_code == 404


def test_pipeline_run_endpoint(monkeypatch: pytest.MonkeyPatch, api_client: TestClient):
    result = SimpleNamespace(
        run_id="run-created",
        status="SUCCESS",
        start_time=datetime(2026, 2, 1),
        end_time=datetime(2026, 2, 1, 0, 1),
        duration_seconds=60.0,
        total_ingested=10,
        total_loaded=8,
        total_quarantined=2,
        metrics_summary={},
        quarantine_summary={},
    )
    monkeypatch.setattr(services, "execute_pipeline", lambda force_mock: result)

    response = api_client.post("/api/v1/pipeline/run")

    assert response.status_code == 201
    assert response.json()["run_id"] == "run-created"


def test_quality_endpoints_and_pagination(api_client: TestClient):
    summary = api_client.get("/api/v1/quality/summary")
    rejected = api_client.get(
        "/api/v1/quality/rejected-records?page=1&page_size=1&run_id=run-test"
    )

    assert summary.status_code == 200
    assert summary.json()["total_rejected_records"] == 1
    assert summary.json()["by_rule"] == {"RULE_1": 1}
    assert rejected.status_code == 200
    assert rejected.json()["data"][0]["record_id"] == "bad-1"


def test_analytics_endpoints(api_client: TestClient):
    revenue = api_client.get(
        "/api/v1/analytics/revenue?start_date=2024-01-01&end_date=2024-01-31"
    )
    products = api_client.get("/api/v1/analytics/top-products?page=1&page_size=5")
    trends = api_client.get("/api/v1/analytics/monthly-trends?page=1&page_size=5")

    assert revenue.status_code == 200
    assert revenue.json()["total_revenue"] == 90.0
    assert revenue.json()["gross_revenue"] == 100.0
    assert products.status_code == 200
    assert products.json()["data"][0]["product_id"] == "PROD-001"
    assert products.json()["data"][0]["net_sales"] == 90.0
    assert trends.status_code == 200
    assert trends.json()["data"][0]["year_month"] == "2024-01"


def test_invalid_pagination_and_date_range_return_422(api_client: TestClient):
    invalid_page = api_client.get("/api/v1/pipeline/runs?page=0")
    invalid_dates = api_client.get(
        "/api/v1/analytics/revenue?start_date=2026-02-01&end_date=2026-01-01"
    )

    assert invalid_page.status_code == 422
    assert invalid_dates.status_code == 422

"""
Unit Tests for Data Ingestion Modules.
"""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path
import pytest

from app.ingestion.api_ingestion import (
    APIIngestionError,
    OrdersAPIIngestor,
)
from app.ingestion.csv_ingestion import CSVIngestionError, CustomerCSVIngestor


def test_customer_csv_ingestion_success(temp_csv_path: Path):
    with open(temp_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["customer_id", "first_name", "last_name", "email", "city", "state", "postal_code", "signup_date"])
        writer.writerow(["CUST-001", "John", "Doe", "john.doe@example.com", "Austin", "TX", "78701", "2023-01-15"])

    ingestor = CustomerCSVIngestor(temp_csv_path)
    records = ingestor.ingest()

    assert len(records) == 1
    rec = records[0]
    assert rec["customer_id"] == "CUST-001"
    assert rec["first_name"] == "John"
    assert rec["_source_system"] == "CSV_CUSTOMERS"
    assert "_record_hash" in rec
    assert len(rec["_record_hash"]) == 64


def test_customer_csv_missing_file_raises():
    ingestor = CustomerCSVIngestor(Path("non_existent_path_404.csv"))
    with pytest.raises(CSVIngestionError):
        ingestor.ingest()


def test_orders_api_response_parsing_and_pagination(
    sample_valid_order, configure_mock_source
):
    orders = []
    for index in range(3):
        order = deepcopy(sample_valid_order)
        order["order_id"] = f"ORD-PAGE-{index}"
        orders.append(order)
    configure_mock_source(orders)
    api_ingestor = OrdersAPIIngestor(force_mock_client=True)
    page_data = api_ingestor.fetch_page(page=1, page_size=2)

    assert "data" in page_data
    assert len(page_data["data"]) == 2
    assert page_data["page"] == 1
    assert page_data["total_records"] == 3

    records = api_ingestor.ingest(page_size=2, max_pages=2)
    assert len(records) == 3
    assert records[0]["_source_system"] == "REST_API_ORDERS"
    assert len(records[0]["_record_hash"]) == 64


def test_malformed_csv_is_reported_as_ingestion_error(temp_csv_path: Path):
    temp_csv_path.write_text('customer_id,first_name\nCUST-1,"unclosed name\n', encoding="utf-8")

    with pytest.raises(CSVIngestionError, match="Failed to read CSV"):
        CustomerCSVIngestor(temp_csv_path).ingest()


def test_empty_csv_returns_empty_batch_with_success_metadata(temp_csv_path: Path):
    temp_csv_path.write_text(
        "customer_id,first_name,last_name,email,city,state,postal_code,signup_date\n",
        encoding="utf-8",
    )

    result = CustomerCSVIngestor(temp_csv_path).ingest_with_metadata()

    assert result.records == [], "An empty CSV should produce an empty batch."
    assert result.metadata.extracted_count == 0
    assert result.metadata.ingestion_status == "SUCCESS"


def test_order_ingestion_reports_partial_page_failure(
    monkeypatch: pytest.MonkeyPatch, sample_valid_order
):
    ingestor = OrdersAPIIngestor(force_mock_client=True)
    valid_page = {
        "page": 1,
        "total_pages": 2,
        "data": [sample_valid_order],
    }

    def fetch_page(page: int, page_size: int = 50):
        if page == 1:
            return valid_page
        raise APIIngestionError("injected page failure")

    monkeypatch.setattr(ingestor, "fetch_page", fetch_page)
    result = ingestor.ingest_with_metadata(page_size=1)

    assert len(result.records) == 1, "Successful first-page records must be retained."
    assert result.metadata.ingestion_status == "PARTIAL"
    assert result.metadata.extracted_count == 1

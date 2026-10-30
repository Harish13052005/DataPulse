"""
Unit Tests for Data Ingestion Modules.
"""

from __future__ import annotations

import csv
from pathlib import Path
import pytest

from app.ingestion.api_ingestion import OrdersAPIIngestor
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


def test_orders_api_ingestion_mock_transport():
    api_ingestor = OrdersAPIIngestor(force_mock_client=True)
    page_data = api_ingestor.fetch_page(page=1, page_size=20)

    assert "data" in page_data
    assert len(page_data["data"]) == 20
    assert page_data["page"] == 1
    assert page_data["total_records"] >= 20

    records = api_ingestor.ingest(page_size=25, max_pages=2)
    assert len(records) == 50
    assert records[0]["_source_system"] == "REST_API_ORDERS"
    assert len(records[0]["_record_hash"]) == 64

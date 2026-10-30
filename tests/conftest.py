"""Isolated test fixtures for DataPulse unit and integration tests."""

from __future__ import annotations

import csv
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings as settings_module
from app.config.settings import settings
from app.warehouse import connection
from app.warehouse.connection import Base
from app.warehouse import models as _models  # noqa: F401
from tests.fixtures.sample_data import (
    SAMPLE_INVALID_CUSTOMER,
    SAMPLE_VALID_CUSTOMER,
    SAMPLE_VALID_ORDER,
)


@pytest.fixture(autouse=True)
def isolate_quarantine_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep test quarantine output out of the application's data directory."""
    quarantine_dir = tmp_path / "quarantine"
    monkeypatch.setattr(settings, "QUARANTINE_DATA_DIR", quarantine_dir)
    monkeypatch.setattr(settings_module.settings, "QUARANTINE_DATA_DIR", quarantine_dir)


@pytest.fixture
def test_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Create a fresh SQLite database per test and route app sessions to it."""
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'test-warehouse.sqlite'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(database_engine, "connect")
    def enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=database_engine)
    factory = sessionmaker(bind=database_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(connection, "engine", database_engine)
    monkeypatch.setattr(connection, "SessionFactory", factory)

    from app.api import app as application_api

    monkeypatch.setattr(application_api, "engine", database_engine)
    yield database_engine
    Base.metadata.drop_all(bind=database_engine)
    database_engine.dispose()


@pytest.fixture
def test_db_session(test_engine) -> Iterator[Session]:
    """Yield a session against the isolated per-test database."""
    factory = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def temp_csv_path(tmp_path: Path) -> Path:
    return tmp_path / "customers.csv"


@pytest.fixture
def sample_valid_customer() -> dict[str, Any]:
    return deepcopy(SAMPLE_VALID_CUSTOMER)


@pytest.fixture
def sample_invalid_customer() -> dict[str, Any]:
    return deepcopy(SAMPLE_INVALID_CUSTOMER)


@pytest.fixture
def sample_valid_order() -> dict[str, Any]:
    return deepcopy(SAMPLE_VALID_ORDER)


@pytest.fixture
def sample_products() -> list[dict[str, Any]]:
    return [
        {
            "product_id": "PROD-001",
            "product_name": "Test Headphones",
            "category": "Electronics",
            "unit_price": 49.99,
        },
        {
            "product_id": "PROD-002",
            "product_name": "Test Monitor",
            "category": "Electronics",
            "unit_price": 150.0,
        },
    ]


@pytest.fixture
def configure_mock_source(monkeypatch: pytest.MonkeyPatch):
    """Replace source-API storage with deterministic test records."""
    from app.api import mock_app

    def _configure(orders: list[dict[str, Any]]) -> None:
        monkeypatch.setattr(
            mock_app,
            "DB",
            {
                "orders": deepcopy(orders),
                "products": deepcopy(mock_app.PRODUCT_CATALOG),
                "initialized": True,
            },
        )

    return _configure


@pytest.fixture
def write_customer_csv():
    """Write supplied customer records to a temporary CSV file."""

    def _write(path: Path, customers: list[dict[str, Any]]) -> Path:
        columns = [
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "city",
            "state",
            "postal_code",
            "country",
            "signup_date",
            "customer_segment",
            "is_active",
        ]
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            for record in customers:
                writer.writerow({key: record.get(key) for key in columns})
        return path

    return _write


@pytest.fixture
def seeded_warehouse(test_db_session: Session, sample_valid_customer: dict[str, Any]):
    """Seed a small, known warehouse dataset for query and API tests."""
    from datetime import date, datetime

    from app.transformation.dimensional_transformer import DimensionalTransformer
    from app.warehouse.loader import WarehouseLoader

    transformer = DimensionalTransformer()
    loader = WarehouseLoader()
    dim_customers = transformer.transform_customers([sample_valid_customer])
    dim_products = transformer.transform_products(
        [
            {
                "product_id": "PROD-001",
                "product_name": "Test Headphones",
                "category": "Electronics",
                "unit_price": 49.99,
            }
        ]
    )
    date_row = transformer.build_date_dimension_record(date(2024, 1, 15))
    fact_order = {
        "order_key": 1001,
        "order_id": "ORD-TEST-1",
        "customer_key": dim_customers[0]["customer_key"],
        "customer_id": sample_valid_customer["customer_id"],
        "order_date_key": date_row["date_key"],
        "order_timestamp": datetime(2024, 1, 15, 12, 0),
        "status": "COMPLETED",
        "payment_method": "CARD",
        "item_count": 1,
        "total_quantity": 2,
        "subtotal": 100.0,
        "tax_amount": 8.0,
        "shipping_fee": 5.0,
        "discount_amount": 10.0,
        "total_amount": 103.0,
        "net_amount": 90.0,
        "ingested_at": "2024-01-15T12:00:00+00:00",
        "record_hash": "order-hash",
    }
    fact_item = {
        "order_item_key": 10001,
        "order_key": fact_order["order_key"],
        "order_id": fact_order["order_id"],
        "product_key": dim_products[0]["product_key"],
        "product_id": dim_products[0]["product_id"],
        "customer_key": dim_customers[0]["customer_key"],
        "order_date_key": date_row["date_key"],
        "quantity": 2,
        "unit_price": 50.0,
        "line_total": 100.0,
        "discount_allocated": 10.0,
    }

    loader.load_customers(test_db_session, dim_customers)
    loader.load_products(test_db_session, dim_products)
    loader.load_date_dimension(test_db_session, [date_row])
    loader.load_orders_and_items(test_db_session, [fact_order], [fact_item])
    test_db_session.commit()
    return {
        "customer": dim_customers[0],
        "product": dim_products[0],
        "date": date_row,
        "order": fact_order,
        "item": fact_item,
    }

"""Integration tests for each local ingestion source and the test warehouse."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.data_generator import PRODUCT_CATALOG
from app.api.mock_app import app as source_api
from app.ingestion.api_ingestion import OrdersAPIIngestor
from app.ingestion.csv_ingestion import CustomerCSVIngestor
from app.transformation.dimensional_transformer import DimensionalTransformer
from app.validation.rules import BusinessRuleValidator
from app.warehouse.loader import WarehouseLoader
from app.warehouse.models import (
    DimCustomer,
    FactOrder,
    FactOrderItem,
)


def _insert_valid_customer(
    session: Session, customer: dict, loader: WarehouseLoader
) -> dict:
    validation = BusinessRuleValidator.validate_customer(customer)
    assert validation.is_valid, f"Test customer unexpectedly failed validation: {validation.violations}"
    dim_customer = DimensionalTransformer.transform_customers([validation.record_data])
    loader.load_customers(session, dim_customer)
    return dim_customer[0]


def _load_order(session: Session, order: dict, dim_customer: dict) -> None:
    validation = BusinessRuleValidator.validate_order(
        order, known_valid_customer_ids={dim_customer["customer_id"]}
    )
    assert validation.is_valid, f"Test order unexpectedly failed validation: {validation.violations}"

    products = DimensionalTransformer.transform_products(PRODUCT_CATALOG)
    product_lookup = {product["product_id"]: product["product_key"] for product in products}
    customer_lookup = {dim_customer["customer_id"]: dim_customer["customer_key"]}
    facts, items, dates = DimensionalTransformer.transform_orders_and_items(
        [validation.record_data], customer_lookup, product_lookup
    )
    loader = WarehouseLoader()
    loader.load_products(session, products)
    loader.load_date_dimension(session, dates)
    loader.load_orders_and_items(session, facts, items)


def test_customer_csv_ingestion_loads_validated_customer_into_warehouse(
    temp_csv_path: Path,
    write_customer_csv,
    sample_valid_customer,
    test_db_session: Session,
):
    write_customer_csv(temp_csv_path, [sample_valid_customer])
    records = CustomerCSVIngestor(temp_csv_path).ingest()
    loader = WarehouseLoader()
    customer = _insert_valid_customer(test_db_session, records[0], loader)
    test_db_session.commit()

    stored = test_db_session.scalar(
        select(DimCustomer).where(DimCustomer.customer_id == customer["customer_id"])
    )
    assert stored is not None, "A valid CSV customer must be persisted in the warehouse."
    assert stored.email == sample_valid_customer["email"]
    assert test_db_session.scalar(select(func.count()).select_from(DimCustomer)) == 1


def test_mock_rest_api_ingestion_loads_order_and_lines_into_warehouse(
    sample_valid_customer,
    sample_valid_order,
    configure_mock_source,
    test_db_session: Session,
):
    configure_mock_source([sample_valid_order])
    with TestClient(source_api) as client:
        page = client.get("/api/v1/orders", params={"page": 1, "page_size": 10})
    assert page.status_code == 200
    assert page.json()["total_records"] == 1

    # Exercise the ingestor's response parsing without network access.
    ingestor = OrdersAPIIngestor(force_mock_client=True)
    ingested_orders = ingestor.ingest(page_size=10)
    assert len(ingested_orders) == 1
    assert ingested_orders[0]["order_id"] == sample_valid_order["order_id"]

    loader = WarehouseLoader()
    dim_customer = _insert_valid_customer(test_db_session, sample_valid_customer, loader)
    _load_order(test_db_session, ingested_orders[0], dim_customer)
    test_db_session.commit()

    assert test_db_session.scalar(select(func.count()).select_from(FactOrder)) == 1
    assert test_db_session.scalar(select(func.count()).select_from(FactOrderItem)) == 2
    stored_order = test_db_session.scalar(
        select(FactOrder).where(FactOrder.order_id == sample_valid_order["order_id"])
    )
    assert stored_order is not None, "The REST source order should exist in the warehouse."
    assert stored_order.total_quantity == 2

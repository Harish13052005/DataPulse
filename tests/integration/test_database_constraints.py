"""Database-level uniqueness and foreign-key enforcement tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.transformation.dimensional_transformer import DimensionalTransformer
from app.warehouse.models import DimCustomer, FactOrder


def test_customer_natural_key_uniqueness_is_enforced(
    test_db_session: Session, sample_valid_customer: dict
):
    customer = DimensionalTransformer.transform_customers([sample_valid_customer])[0]
    test_db_session.add(DimCustomer(**customer))
    test_db_session.commit()

    duplicate = {**customer, "customer_key": customer["customer_key"] + 1}
    test_db_session.add(DimCustomer(**duplicate))
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        test_db_session.commit()
    test_db_session.rollback()

    assert test_db_session.query(DimCustomer).count() == 1, (
        "A duplicate natural customer ID must not be persisted."
    )


def test_order_customer_foreign_key_is_enforced(test_db_session: Session):
    test_db_session.add(
        FactOrder(
            order_key=7001,
            order_id="ORD-MISSING-CUSTOMER",
            customer_key=7999,
            customer_id="CUST-MISSING",
            order_date_key=20240101,
            order_timestamp=datetime(2024, 1, 1),
            status="COMPLETED",
            payment_method="CARD",
            item_count=0,
            total_quantity=0,
            subtotal=0,
            tax_amount=0,
            shipping_fee=0,
            discount_amount=0,
            total_amount=0,
            net_amount=0,
            ingested_at="2024-01-01T00:00:00Z",
            record_hash="missing-customer",
        )
    )

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        test_db_session.commit()
    test_db_session.rollback()

    assert test_db_session.query(FactOrder).count() == 0, (
        "An order with an unknown customer key must not be stored."
    )

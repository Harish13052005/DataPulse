"""
Unit & Idempotency Tests for Data Warehouse Loader.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from app.warehouse.loader import WarehouseLoader
from app.warehouse.models import DimCustomer


def test_warehouse_loader_idempotency_customers(test_db_session: Session):
    loader = WarehouseLoader()

    customer_dict = {
        "customer_key": 1001,
        "customer_id": "CUST-1001",
        "first_name": "Bob",
        "last_name": "Marley",
        "full_name": "Bob Marley",
        "email": "bob@example.com",
        "phone": "+1-555-1234",
        "address": "1 Love St",
        "city": "Miami",
        "state": "FL",
        "postal_code": "33101",
        "country": "USA",
        "signup_date": date(2023, 2, 1),
        "signup_year": 2023,
        "signup_month": 2,
        "customer_segment": "Standard",
        "is_active": True,
        "ingested_at": "2023-02-01T00:00:00Z",
        "record_hash": "testhash12345",
        "updated_at": datetime.now(timezone.utc)
    }

    # First load
    ins, upd, unch = loader.load_customers(test_db_session, [customer_dict])
    test_db_session.commit()
    assert ins == 1
    assert upd == 0
    assert unch == 0

    assert test_db_session.query(DimCustomer).count() == 1

    # Second load (identical data)
    ins2, upd2, unch2 = loader.load_customers(test_db_session, [customer_dict])
    test_db_session.commit()
    assert ins2 == 0
    assert upd2 == 0
    assert unch2 == 1

    assert test_db_session.query(DimCustomer).count() == 1


def test_warehouse_loader_update_changed_record(test_db_session: Session):
    loader = WarehouseLoader()

    customer_dict = {
        "customer_key": 1002,
        "customer_id": "CUST-1002",
        "first_name": "Charlie",
        "last_name": "Brown",
        "full_name": "Charlie Brown",
        "email": "charlie@example.com",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78701",
        "country": "USA",
        "signup_date": date(2023, 3, 1),
        "signup_year": 2023,
        "signup_month": 3,
        "customer_segment": "Standard",
        "is_active": True,
        "ingested_at": "2023-03-01T00:00:00Z",
        "record_hash": "originalhash",
        "updated_at": datetime.now(timezone.utc)
    }

    loader.load_customers(test_db_session, [customer_dict])
    test_db_session.commit()

    modified = customer_dict.copy()
    modified["email"] = "charlie.new@example.com"
    modified["record_hash"] = "newupdatedhash"

    ins, upd, unch = loader.load_customers(test_db_session, [modified])
    test_db_session.commit()
    assert ins == 0
    assert upd == 1
    assert unch == 0

    cust_row = test_db_session.query(DimCustomer).filter_by(customer_id="CUST-1002").first()
    assert cust_row.email == "charlie.new@example.com"
    assert cust_row.record_hash == "newupdatedhash"
    assert test_db_session.query(DimCustomer).count() == 1

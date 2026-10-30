"""Unit tests for warehouse merge and idempotency behavior."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.warehouse.loader import WarehouseLoader
from app.warehouse.models import DimCustomer


def _customer(customer_id: str = "CUST-1001") -> dict:
    return {
        "customer_key": 1001,
        "customer_id": customer_id,
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
        "updated_at": datetime(2023, 2, 1, tzinfo=timezone.utc),
    }


def test_identical_customer_load_is_idempotent(test_db_session: Session):
    loader = WarehouseLoader()
    customer = _customer()

    first = loader.load_customers(test_db_session, [customer])
    test_db_session.commit()
    second = loader.load_customers(test_db_session, [customer])
    test_db_session.commit()

    assert first == (1, 0, 0), "First load should insert one dimension row."
    assert second == (0, 0, 1), "Repeated identical input should remain unchanged."
    assert test_db_session.query(DimCustomer).count() == 1


def test_changed_customer_record_updates_existing_row(test_db_session: Session):
    loader = WarehouseLoader()
    customer = _customer("CUST-1002")
    loader.load_customers(test_db_session, [customer])
    test_db_session.commit()

    updated = {**customer, "email": "bob.updated@example.com", "record_hash": "new-hash"}
    counts = loader.load_customers(test_db_session, [updated])
    test_db_session.commit()

    stored = test_db_session.query(DimCustomer).filter_by(customer_id="CUST-1002").one()
    assert counts == (0, 1, 0), "Changed input should update the existing dimension row."
    assert stored.email == "bob.updated@example.com"
    assert stored.record_hash == "new-hash"
    assert test_db_session.query(DimCustomer).count() == 1


def test_customer_batch_uses_bounded_selects_instead_of_one_lookup_per_row(
    test_db_session: Session, test_engine
):
    loader = WarehouseLoader()
    customers = [
        {**_customer(f"CUST-BATCH-{index:03d}"), "customer_key": 2000 + index}
        for index in range(25)
    ]
    select_count = 0

    def count_selects(_connection, _cursor, statement, _parameters, _context, _executemany):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(test_engine, "before_cursor_execute", count_selects)
    try:
        counts = loader.load_customers(test_db_session, customers)
        test_db_session.commit()
    finally:
        event.remove(test_engine, "before_cursor_execute", count_selects)

    assert counts == (25, 0, 0)
    assert select_count == 1, (
        "A customer batch should prefetch existing keys in one SELECT, "
        "not issue one SELECT per row."
    )

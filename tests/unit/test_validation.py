"""Unit tests for schema, domain, duplicate, and quality validation."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.config.settings import settings
from app.ingestion.ingestion_meta import RunMetadata
from app.validation.engine import (
    compute_quality_metrics,
    validate_customers,
    validate_orders,
)
from app.validation.quarantine import QuarantineManager
from app.validation.rules import BusinessRuleValidator
from app.validation.schemas import CustomerRawSchema, OrderRawSchema


def test_customer_schema_normalizes_email_and_optional_nulls(sample_valid_customer):
    sample_valid_customer["email"] = "  ALICE@EXAMPLE.COM  "
    sample_valid_customer["phone"] = None

    customer = CustomerRawSchema(**sample_valid_customer)

    assert customer.email == "alice@example.com"
    assert customer.phone is None, "A nullable optional field should remain null."


def test_customer_schema_rejects_missing_required_field(sample_valid_customer):
    del sample_valid_customer["email"]

    with pytest.raises(ValidationError, match="email"):
        CustomerRawSchema(**sample_valid_customer)


def test_customer_schema_rejects_null_required_field(sample_valid_customer):
    sample_valid_customer["first_name"] = None

    with pytest.raises(ValidationError, match="first_name"):
        CustomerRawSchema(**sample_valid_customer)


def test_customer_schema_rejects_invalid_email(sample_valid_customer):
    sample_valid_customer["email"] = "not-an-email"

    with pytest.raises(ValidationError, match="Invalid email"):
        CustomerRawSchema(**sample_valid_customer)


def test_customer_schema_rejects_future_signup_date(sample_valid_customer):
    sample_valid_customer["signup_date"] = "2099-12-31"

    with pytest.raises(ValidationError, match="future"):
        CustomerRawSchema(**sample_valid_customer)


def test_customer_validation_rejects_unexpected_schema_field(sample_valid_customer):
    sample_valid_customer["unexpected_column"] = "schema drift"
    result = validate_customers([sample_valid_customer], RunMetadata(run_id="schema-run"))

    assert result.records == [], "Schema drift should quarantine, not accept, the row."
    assert "Unexpected fields" in settings_quarantine_text()


def settings_quarantine_text() -> str:
    from app.config.settings import settings

    files = list(settings.QUARANTINE_DATA_DIR.glob("*.jsonl"))
    assert files, "Rejected schema drift should create an audit quarantine file."
    return files[0].read_text(encoding="utf-8")


def test_duplicate_customer_ids_are_quarantined(sample_valid_customer):
    second = deepcopy(sample_valid_customer)
    second["email"] = "duplicate@example.com"
    result = validate_customers(
        [sample_valid_customer, second], RunMetadata(run_id="duplicate-customer-run")
    )

    assert len(result.records) == 1, "Only the first occurrence of an ID should be retained."
    quarantine_text = settings_quarantine_text()
    assert "Duplicate customer_id" in quarantine_text


def test_order_schema_rejects_negative_quantity(sample_valid_order):
    sample_valid_order["items"][0]["quantity"] = -1

    with pytest.raises(ValidationError, match="greater than 0"):
        OrderRawSchema(**sample_valid_order)


def test_order_validation_rejects_negative_and_over_limit_discounts(
    sample_valid_order,
):
    for discount in (-1.0, 101.0):
        order = deepcopy(sample_valid_order)
        order["discount_amount"] = discount
        result = validate_orders(
            [order],
            {order["customer_id"]},
            RunMetadata(run_id=f"discount-{discount}"),
        )
        assert result.records == [], f"Invalid discount {discount} must be rejected."
    assert "Discount amount out of allowed range" in settings_quarantine_text()


def test_duplicate_order_and_order_line_ids_are_quarantined(
    sample_valid_order,
):
    repeated_order = deepcopy(sample_valid_order)
    result = validate_orders(
        [sample_valid_order, repeated_order],
        {sample_valid_order["customer_id"]},
        RunMetadata(run_id="duplicate-order-run"),
    )
    assert len(result.records) == 1, "Duplicate order IDs must not load twice."
    assert "Duplicate order_id" in settings_quarantine_text()

    duplicate_line = deepcopy(sample_valid_order)
    duplicate_line["items"][1]["item_id"] = duplicate_line["items"][0]["item_id"]
    line_result = validate_orders(
        [duplicate_line],
        {duplicate_line["customer_id"]},
        RunMetadata(run_id="duplicate-line-run"),
    )
    assert line_result.records == [], "A repeated line ID within an order must be rejected."
    assert "Duplicate item_id" in settings_quarantine_text()


def test_invalid_customer_foreign_key_is_quarantined(sample_valid_order):
    result = validate_orders(
        [sample_valid_order],
        {"CUST-OTHER"},
        RunMetadata(run_id="invalid-fk-run"),
    )

    assert result.records == [], "Orders referencing unknown customers must be rejected."
    assert "Invalid customer_id reference" in settings_quarantine_text()


def test_business_rule_validator_reports_customer_and_order_errors(
    sample_invalid_customer, sample_valid_order
):
    customer_result = BusinessRuleValidator.validate_customer(sample_invalid_customer)
    order = deepcopy(sample_valid_order)
    order["total_amount"] = -50
    order_result = BusinessRuleValidator.validate_order(order)

    assert not customer_result.is_valid
    assert any(v.rule_code.startswith("BR_CUST") for v in customer_result.violations)
    assert not order_result.is_valid
    assert any(v.rule_code == "BR_ORD_002" for v in order_result.violations)


def test_quarantine_manager_records_rejection_categories(sample_invalid_customer):
    manager = QuarantineManager()
    manager.record_quarantine(BusinessRuleValidator.validate_customer(sample_invalid_customer))

    records = manager.get_records()
    summary = manager.get_summary()

    assert records, "Rejected records should remain available for audit."
    assert records[0]["record_id"] == "CUST-9002"
    assert summary["total_quarantined_entries"] == len(records)
    assert summary["by_source"]["CSV_CUSTOMERS"] == len(records)


@pytest.mark.parametrize(
    ("total", "valid", "rejected", "expected_pct"),
    [(10, 8, 2, 80.0), (0, 0, 0, 0.0), (4, 0, 4, 0.0)],
)
def test_data_quality_percentage_handles_empty_and_rejected_batches(
    total, valid, rejected, expected_pct
):
    metrics = compute_quality_metrics(
        total=total,
        valid=valid,
        rejected=rejected,
        duplicate=1 if rejected else 0,
        null_violations=0,
        referential=0,
    )

    assert metrics["data_quality_percentage"] == expected_pct
    assert metrics["valid_records"] + metrics["rejected_records"] == total

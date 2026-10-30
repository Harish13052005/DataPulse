"""
Unit Tests for Schema & Business Rule Validation and Quarantine Routing.
"""

from __future__ import annotations

import pytest
from app.validation.quarantine import QuarantineManager
from app.validation.rules import BusinessRuleValidator
from app.validation.schemas import CustomerRawSchema, OrderRawSchema


def test_customer_schema_valid(sample_valid_customer):
    model = CustomerRawSchema(**sample_valid_customer)
    assert model.customer_id == "CUST-9001"
    assert model.email == "alice.walker@example.com"


def test_customer_schema_invalid_email(sample_valid_customer):
    invalid = sample_valid_customer.copy()
    invalid["email"] = "bad-email-without-at"
    with pytest.raises(Exception):
        CustomerRawSchema(**invalid)


def test_customer_schema_future_date_rejected(sample_valid_customer):
    invalid = sample_valid_customer.copy()
    invalid["signup_date"] = "2099-12-31"
    with pytest.raises(Exception):
        CustomerRawSchema(**invalid)


def test_business_rule_validator_valid_customer(sample_valid_customer):
    res = BusinessRuleValidator.validate_customer(sample_valid_customer)
    assert res.is_valid is True
    assert len(res.violations) == 0


def test_business_rule_validator_invalid_customer(sample_invalid_customer):
    res = BusinessRuleValidator.validate_customer(sample_invalid_customer)
    assert res.is_valid is False
    assert len(res.violations) > 0
    rule_codes = [v.rule_code for v in res.violations]
    assert "BR_CUST_SCHEMA" in rule_codes or "BR_CUST_001" in rule_codes


def test_order_referential_integrity_violation(sample_valid_order):
    known_customers = {"CUST-0001", "CUST-0002"}
    res = BusinessRuleValidator.validate_order(sample_valid_order, known_valid_customer_ids=known_customers)
    assert res.is_valid is False
    rule_codes = [v.rule_code for v in res.violations]
    assert "BR_REF_001" in rule_codes


def test_order_negative_amount_violation(sample_valid_order):
    bad_order = sample_valid_order.copy()
    bad_order["total_amount"] = -50.00
    res = BusinessRuleValidator.validate_order(bad_order)
    assert res.is_valid is False
    rule_codes = [v.rule_code for v in res.violations]
    assert "BR_ORD_002" in rule_codes or "BR_ORD_SCHEMA" in rule_codes


def test_quarantine_manager_logging_and_summary(sample_invalid_customer):
    qm = QuarantineManager()
    qm.clear()

    res = BusinessRuleValidator.validate_customer(sample_invalid_customer)
    qm.record_quarantine(res)

    records = qm.get_records()
    assert len(records) > 0
    assert records[0]["record_id"] == "CUST-9002"
    assert records[0]["source_system"] == "CSV_CUSTOMERS"

    summary = qm.get_summary()
    assert summary["total_quarantined_entries"] > 0
    assert "CSV_CUSTOMERS" in summary["by_source"]

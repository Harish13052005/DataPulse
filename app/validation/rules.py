"""
Business Rule Engine and Domain Validation for DataPulse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from pydantic import ValidationError

from app.validation.schemas import CustomerRawSchema, OrderRawSchema


@dataclass
class RuleViolation:
    rule_code: str
    field_name: str
    error_type: str
    message: str


@dataclass
class ValidationRecordResult:
    record_id: str
    source_system: str
    is_valid: bool
    raw_payload: str
    record_data: Dict[str, Any]
    violations: List[RuleViolation] = field(default_factory=list)


class BusinessRuleValidator:
    """Applies schema and domain business rules to ingested datasets."""

    @staticmethod
    def validate_customer(record: Dict[str, Any]) -> ValidationRecordResult:
        """Validate a single customer record."""
        record_id = str(record.get("customer_id", "UNKNOWN"))
        source_system = record.get("_source_system", "CSV_CUSTOMERS")
        raw_payload = record.get("_raw_payload", str(record))
        violations: List[RuleViolation] = []

        try:
            validated = CustomerRawSchema(**record)
            clean_dict = validated.model_dump()
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                violations.append(
                    RuleViolation(
                        rule_code="BR_CUST_SCHEMA",
                        field_name=loc,
                        error_type="SCHEMA_VALIDATION_ERROR",
                        message=err["msg"]
                    )
                )
            clean_dict = record

        # Business Rule BR_CUST_001: Email check
        email = str(clean_dict.get("email", "")).strip()
        if not email or "@" not in email or "." not in email:
            violations.append(
                RuleViolation(
                    rule_code="BR_CUST_001",
                    field_name="email",
                    error_type="BUSINESS_RULE_VIOLATION",
                    message=f"Customer email '{email}' is malformed or invalid."
                )
            )

        # Business Rule BR_CUST_003: Mandatory first/last name
        if not str(clean_dict.get("first_name", "")).strip() or not str(clean_dict.get("last_name", "")).strip():
            violations.append(
                RuleViolation(
                    rule_code="BR_CUST_003",
                    field_name="name",
                    error_type="BUSINESS_RULE_VIOLATION",
                    message="First name and last name must not be blank."
                )
            )

        # Business Rule BR_CUST_004: State code 2 letters
        state = str(clean_dict.get("state", "")).strip().upper()
        if len(state) != 2:
            violations.append(
                RuleViolation(
                    rule_code="BR_CUST_004",
                    field_name="state",
                    error_type="BUSINESS_RULE_VIOLATION",
                    message=f"State code '{state}' must be a 2-letter abbreviation."
                )
            )

        return ValidationRecordResult(
            record_id=record_id,
            source_system=source_system,
            is_valid=len(violations) == 0,
            raw_payload=raw_payload,
            record_data=clean_dict,
            violations=violations
        )

    @staticmethod
    def validate_order(
        record: Dict[str, Any],
        known_valid_customer_ids: Optional[Set[str]] = None
    ) -> ValidationRecordResult:
        """Validate order and check referential integrity against customers."""
        order_id = str(record.get("order_id", "UNKNOWN"))
        source_system = record.get("_source_system", "REST_API_ORDERS")
        raw_payload = record.get("_raw_payload", str(record))
        violations: List[RuleViolation] = []

        try:
            validated = OrderRawSchema(**record)
            clean_dict = validated.model_dump()
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                violations.append(
                    RuleViolation(
                        rule_code="BR_ORD_SCHEMA",
                        field_name=loc,
                        error_type="SCHEMA_VALIDATION_ERROR",
                        message=err["msg"]
                    )
                )
            clean_dict = record

        # Referential Integrity: BR_REF_001
        cust_id = str(clean_dict.get("customer_id", ""))
        if known_valid_customer_ids is not None and cust_id not in known_valid_customer_ids:
            violations.append(
                RuleViolation(
                    rule_code="BR_REF_001",
                    field_name="customer_id",
                    error_type="REFERENTIAL_INTEGRITY_VIOLATION",
                    message=f"Customer ID '{cust_id}' does not exist in valid customer records."
                )
            )

        # Financial Consistency: BR_ORD_002
        total_amount = float(clean_dict.get("total_amount", 0.0) or 0.0)
        if total_amount < 0:
            violations.append(
                RuleViolation(
                    rule_code="BR_ORD_002",
                    field_name="total_amount",
                    error_type="BUSINESS_RULE_VIOLATION",
                    message=f"Total amount cannot be negative: {total_amount}"
                )
            )

        # Positive line item items: BR_ORD_003
        items = clean_dict.get("items", [])
        if not items:
            violations.append(
                RuleViolation(
                    rule_code="BR_ORD_004",
                    field_name="items",
                    error_type="BUSINESS_RULE_VIOLATION",
                    message="Order must contain at least one line item."
                )
            )
        else:
            for idx, item in enumerate(items):
                qty = item.get("quantity", 0)
                price = item.get("unit_price", 0.0)
                if qty <= 0:
                    violations.append(
                        RuleViolation(
                            rule_code="BR_ORD_003",
                            field_name=f"items[{idx}].quantity",
                            error_type="BUSINESS_RULE_VIOLATION",
                            message=f"Item quantity must be > 0. Found: {qty}"
                        )
                    )
                if price <= 0.0:
                    violations.append(
                        RuleViolation(
                            rule_code="BR_ORD_003",
                            field_name=f"items[{idx}].unit_price",
                            error_type="BUSINESS_RULE_VIOLATION",
                            message=f"Item unit price must be > 0. Found: {price}"
                        )
                    )

        return ValidationRecordResult(
            record_id=order_id,
            source_system=source_system,
            is_valid=len(violations) == 0,
            raw_payload=raw_payload,
            record_data=clean_dict,
            violations=violations
        )

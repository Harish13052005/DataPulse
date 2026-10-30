"""
Validation Schemas using Pydantic V2 for DataPulse Ingestion Sources.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class CustomerRawSchema(BaseModel):
    """Schema validation for incoming customer record."""
    customer_id: str = Field(..., min_length=3)
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=5)
    phone: Optional[str] = None
    address: Optional[str] = None
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=2, max_length=2)
    postal_code: str = Field(..., min_length=3)
    country: str = Field(default="USA")
    signup_date: str = Field(..., description="YYYY-MM-DD")
    customer_segment: str = Field(default="Standard")
    is_active: bool = Field(default=True)

    # Ingestion metadata
    _source_system: Optional[str] = None
    _source_file: Optional[str] = None
    _source_row_num: Optional[int] = None
    _ingested_at: Optional[str] = None
    _record_hash: Optional[str] = None
    _raw_payload: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email_syntax(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v.strip()):
            raise ValueError(f"Invalid email address syntax: '{v}'")
        return v.strip().lower()

    @field_validator("signup_date")
    @classmethod
    def validate_signup_date_format(cls, v: str) -> str:
        try:
            d = datetime.strptime(v.strip(), "%Y-%m-%d").date()
        except ValueError as err:
            raise ValueError(f"Invalid date format for signup_date: '{v}'. Expected YYYY-MM-DD.") from err

        if d > date.today():
            raise ValueError(f"Signup date cannot be in the future: '{v}'")
        return v.strip()


class LineItemRawSchema(BaseModel):
    """Schema validation for an individual line item."""
    item_id: str = Field(..., min_length=3)
    product_id: str = Field(..., min_length=3)
    product_name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0.0)
    line_total: float = Field(..., ge=0.0)


class OrderRawSchema(BaseModel):
    """Schema validation for incoming order with nested line items."""
    order_id: str = Field(..., min_length=3)
    customer_id: str = Field(..., min_length=3)
    order_timestamp: str = Field(..., description="ISO 8601 UTC")
    status: str = Field(...)
    payment_method: str = Field(..., min_length=2)
    subtotal: float = Field(..., ge=0.0)
    tax_amount: float = Field(..., ge=0.0)
    shipping_fee: float = Field(..., ge=0.0)
    discount_amount: float = Field(default=0.0, ge=0.0)
    total_amount: float = Field(..., ge=0.0)
    items: List[LineItemRawSchema] = Field(..., min_length=1)

    # Ingestion metadata
    _source_system: Optional[str] = None
    _source_page: Optional[int] = None
    _source_row_num: Optional[int] = None
    _ingested_at: Optional[str] = None
    _record_hash: Optional[str] = None
    _raw_payload: Optional[str] = None

    @field_validator("order_timestamp")
    @classmethod
    def validate_timestamp_format(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except Exception as err:
            raise ValueError(f"Invalid ISO 8601 timestamp: '{v}'") from err
        return v.strip()

    @field_validator("status")
    @classmethod
    def validate_status_enum(cls, v: str) -> str:
        valid_statuses = {"COMPLETED", "PENDING", "CANCELLED", "REFUNDED"}
        clean = v.strip().upper()
        if clean not in valid_statuses:
            raise ValueError(f"Invalid order status: '{v}'. Must be one of {valid_statuses}")
        return clean

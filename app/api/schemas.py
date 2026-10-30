"""Pydantic contracts for the warehouse-facing application API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    page: int
    page_size: int
    total_records: int
    total_pages: int
    data: list[T]


class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    pipeline_name: str
    start_time: datetime
    end_time: datetime | None
    duration_seconds: float | None
    status: str
    records_ingested: int
    valid_records_loaded: int
    quarantined_records: int
    details_json: str | None


class RunRequest(BaseModel):
    force_mock_api_client: bool = Field(
        default=True,
        description="Use the in-process mock source API instead of an HTTP source.",
    )


class RunResponse(BaseModel):
    run_id: str
    status: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    total_ingested: int
    total_loaded: int
    total_quarantined: int
    metrics_summary: dict[str, Any]
    quarantine_summary: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str


class QualitySummaryResponse(BaseModel):
    total_rejected_records: int
    by_rule: dict[str, int]
    by_source: dict[str, int]


class RejectedRecordResponse(BaseModel):
    id: int
    run_id: str | None
    record_id: str
    source_system: str
    error_type: str
    rule_code: str
    field_name: str | None
    error_message: str
    raw_payload: str
    quarantined_at: datetime


class RevenueResponse(BaseModel):
    start_date: date | None
    end_date: date | None
    currency: str = "USD"
    total_orders: int
    completed_orders: int
    gross_revenue: float
    total_revenue: float
    average_order_value: float


class TopProductResponse(BaseModel):
    product_id: str
    product_name: str
    category: str
    total_orders: int
    total_units_sold: int
    gross_sales: float
    total_discounts: float
    net_sales: float


class MonthlyTrendResponse(BaseModel):
    year: int
    month_num: int
    year_month: str
    total_orders: int
    completed_orders: int
    gross_revenue: float
    total_revenue: float
    average_order_value: float

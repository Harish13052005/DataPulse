"""HTTP routes for the DataPulse warehouse application API."""

from __future__ import annotations

import logging
from datetime import date
from typing import Generator

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import services
from app.api.schemas import (
    HealthResponse,
    MonthlyTrendResponse,
    PageResponse,
    PipelineRunResponse,
    QualitySummaryResponse,
    RejectedRecordResponse,
    RevenueResponse,
    RunRequest,
    RunResponse,
    TopProductResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db() -> Generator[Session, None, None]:
    from app.warehouse.connection import SessionFactory

    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@router.get("/health", response_model=HealthResponse, tags=["System"])
def health(session: Session = Depends(get_db)) -> HealthResponse:
    session.execute(text("SELECT 1"))
    return HealthResponse(status="healthy", service="datapulse-application-api", database="connected")


@router.get(
    "/api/v1/pipeline/runs",
    response_model=PageResponse[PipelineRunResponse],
    tags=["Pipeline"],
)
def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> dict:
    return services.list_pipeline_runs(session, page, page_size)


@router.get(
    "/api/v1/pipeline/runs/{run_id}",
    response_model=PipelineRunResponse,
    tags=["Pipeline"],
)
def get_run(run_id: str, session: Session = Depends(get_db)) -> PipelineRunResponse:
    run = services.get_pipeline_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' was not found.")
    return run


@router.post(
    "/api/v1/pipeline/run",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Pipeline"],
)
def run_pipeline(request: RunRequest = Body(default=RunRequest())) -> RunResponse:
    try:
        result = services.execute_pipeline(request.force_mock_api_client)
        return RunResponse(
            run_id=result.run_id,
            status=result.status,
            start_time=result.start_time,
            end_time=result.end_time,
            duration_seconds=result.duration_seconds,
            total_ingested=result.total_ingested,
            total_loaded=result.total_loaded,
            total_quarantined=result.total_quarantined,
            metrics_summary=result.metrics_summary,
            quarantine_summary=result.quarantine_summary,
        )
    except Exception as exc:
        logger.exception("Pipeline execution failed through the application API")
        raise HTTPException(status_code=500, detail="Pipeline execution failed.") from exc


@router.get(
    "/api/v1/quality/summary",
    response_model=QualitySummaryResponse,
    tags=["Quality"],
)
def get_quality_summary(session: Session = Depends(get_db)) -> dict:
    return services.quality_summary(session)


@router.get(
    "/api/v1/quality/rejected-records",
    response_model=PageResponse[RejectedRecordResponse],
    tags=["Quality"],
)
def get_rejected_records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    run_id: str | None = Query(default=None, min_length=1, max_length=64),
    session: Session = Depends(get_db),
) -> dict:
    return services.rejected_records(session, page, page_size, run_id)


@router.get(
    "/api/v1/analytics/revenue",
    response_model=RevenueResponse,
    tags=["Analytics"],
)
def get_revenue(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    return services.revenue_summary(session, start_date, end_date)


@router.get(
    "/api/v1/analytics/top-products",
    response_model=PageResponse[TopProductResponse],
    tags=["Analytics"],
)
def get_top_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_db),
) -> dict:
    return services.top_products(session, page, page_size)


@router.get(
    "/api/v1/analytics/monthly-trends",
    response_model=PageResponse[MonthlyTrendResponse],
    tags=["Analytics"],
)
def get_monthly_trends(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    session: Session = Depends(get_db),
) -> dict:
    return services.monthly_trends(session, page, page_size)

"""Database-backed application API operations."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.pipeline import DataPulsePipeline, PipelineExecutionResult
from app.warehouse.models import (
    DimDate,
    DimProduct,
    FactOrder,
    FactOrderItem,
    PipelineRun,
    QuarantineRecord,
)

def _page(query: Any, session: Session, page: int, page_size: int) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "page": page,
        "page_size": page_size,
        "total_records": total,
        "total_pages": max(1, math.ceil(total / page_size)),
        "data": rows,
    }


def list_pipeline_runs(session: Session, page: int, page_size: int) -> dict[str, Any]:
    query = select(PipelineRun).order_by(PipelineRun.start_time.desc())
    return _page(query, session, page, page_size)


def get_pipeline_run(session: Session, run_id: str) -> PipelineRun | None:
    return session.get(PipelineRun, run_id)


def execute_pipeline(force_mock_api_client: bool) -> PipelineExecutionResult:
    return DataPulsePipeline(force_mock_api_client=force_mock_api_client).run()


def quality_summary(session: Session) -> dict[str, Any]:
    total = session.scalar(select(func.count(QuarantineRecord.id))) or 0
    rules = session.execute(
        select(QuarantineRecord.rule_code, func.count(QuarantineRecord.id))
        .group_by(QuarantineRecord.rule_code)
    ).all()
    sources = session.execute(
        select(QuarantineRecord.source_system, func.count(QuarantineRecord.id))
        .group_by(QuarantineRecord.source_system)
    ).all()
    return {
        "total_rejected_records": total,
        "by_rule": {rule: count for rule, count in rules},
        "by_source": {source: count for source, count in sources},
    }


def rejected_records(
    session: Session, page: int, page_size: int, run_id: str | None
) -> dict[str, Any]:
    query = select(QuarantineRecord)
    if run_id is not None:
        query = query.where(QuarantineRecord.run_id == run_id)
    query = query.order_by(QuarantineRecord.quarantined_at.desc(), QuarantineRecord.id.desc())
    return _page(query, session, page, page_size)


def revenue_summary(
    session: Session, start_date: date | None, end_date: date | None
) -> dict[str, Any]:
    filters = []
    if start_date is not None:
        filters.append(FactOrder.order_timestamp >= datetime.combine(start_date, time.min))
    if end_date is not None:
        filters.append(
            FactOrder.order_timestamp < datetime.combine(end_date + timedelta(days=1), time.min)
        )
    completed = FactOrder.status == "COMPLETED"
    row = session.execute(
        select(
            func.count(FactOrder.order_key),
            func.sum(case((completed, 1), else_=0)),
            func.coalesce(func.sum(case((completed, FactOrder.subtotal), else_=0.0)), 0.0),
            func.coalesce(func.sum(case((completed, FactOrder.net_amount), else_=0.0)), 0.0),
            func.coalesce(func.avg(case((completed, FactOrder.net_amount), else_=None)), 0.0),
        ).where(*filters)
    ).one()
    return {
        "start_date": start_date,
        "end_date": end_date,
        "currency": "USD",
        "total_orders": row[0] or 0,
        "completed_orders": row[1] or 0,
        "gross_revenue": round(float(row[2] or 0), 2),
        "total_revenue": round(float(row[3] or 0), 2),
        "average_order_value": round(float(row[4] or 0), 2),
    }


def top_products(session: Session, page: int, page_size: int) -> dict[str, Any]:
    query = (
        select(
            DimProduct.product_id.label("product_id"),
            DimProduct.product_name.label("product_name"),
            DimProduct.category.label("category"),
            func.count(func.distinct(FactOrderItem.order_key)).label("total_orders"),
            func.coalesce(func.sum(FactOrderItem.quantity), 0).label("total_units_sold"),
            func.coalesce(func.sum(FactOrderItem.line_total), 0.0).label("gross_sales"),
            func.coalesce(func.sum(FactOrderItem.discount_allocated), 0.0).label("total_discounts"),
            func.coalesce(
                func.sum(FactOrderItem.line_total - FactOrderItem.discount_allocated), 0.0
            ).label("net_sales"),
        )
        .join(FactOrderItem, FactOrderItem.product_key == DimProduct.product_key)
        .join(FactOrder, FactOrder.order_key == FactOrderItem.order_key)
        .where(FactOrder.status == "COMPLETED")
        .group_by(DimProduct.product_id, DimProduct.product_name, DimProduct.category)
        .order_by(func.sum(FactOrderItem.line_total - FactOrderItem.discount_allocated).desc())
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    ).mappings().all()
    return {
        "page": page,
        "page_size": page_size,
        "total_records": total,
        "total_pages": max(1, math.ceil(total / page_size)),
        "data": [dict(row) for row in rows],
    }


def monthly_trends(session: Session, page: int, page_size: int) -> dict[str, Any]:
    query = (
        select(
            DimDate.year.label("year"),
            DimDate.month_num.label("month_num"),
            func.count(FactOrder.order_key).label("total_orders"),
            func.sum(case((FactOrder.status == "COMPLETED", 1), else_=0)).label("completed_orders"),
            func.coalesce(
                func.sum(case((FactOrder.status == "COMPLETED", FactOrder.subtotal), else_=0.0)), 0.0
            ).label("gross_revenue"),
            func.coalesce(
                func.sum(case((FactOrder.status == "COMPLETED", FactOrder.net_amount), else_=0.0)), 0.0
            ).label("total_revenue"),
            func.coalesce(
                func.avg(case((FactOrder.status == "COMPLETED", FactOrder.net_amount), else_=None)), 0.0
            ).label("average_order_value"),
        )
        .join(FactOrder, FactOrder.order_date_key == DimDate.date_key)
        .group_by(DimDate.year, DimDate.month_num)
        .order_by(DimDate.year, DimDate.month_num)
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()
    data = [
        {
            "year": row.year,
            "month_num": row.month_num,
            "year_month": f"{row.year:04d}-{row.month_num:02d}",
            "total_orders": row.total_orders,
            "completed_orders": row.completed_orders or 0,
            "gross_revenue": round(float(row.gross_revenue or 0), 2),
            "total_revenue": round(float(row.total_revenue or 0), 2),
            "average_order_value": round(float(row.average_order_value or 0), 2),
        }
        for row in rows
    ]
    return {
        "page": page,
        "page_size": page_size,
        "total_records": total,
        "total_pages": max(1, math.ceil(total / page_size)),
        "data": data,
    }

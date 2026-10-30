"""
Mock source API for E-Commerce Orders and Transactions (Source 2).

Provides pagination, filtering, health checks, and deterministic seed generation.
"""

from __future__ import annotations

import math
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.config.settings import settings
from app.api.data_generator import (
    PRODUCT_CATALOG,
    generate_synthetic_customers,
    generate_synthetic_orders,
)

DB: Dict[str, Any] = {
    "orders": [],
    "products": PRODUCT_CATALOG,
    "initialized": False,
}


def init_mock_database(seed: int = 42, count: int = 1000, dirty_ratio: float = 0.08) -> None:
    """Initialize deterministic mock orders data store."""
    customers = generate_synthetic_customers(count=250, seed=seed, dirty_ratio=0.0)
    customer_ids = [c["customer_id"] for c in customers]
    orders = generate_synthetic_orders(
        count=count,
        customer_ids=customer_ids,
        seed=seed,
        dirty_ratio=dirty_ratio
    )
    DB["orders"] = orders
    DB["products"] = PRODUCT_CATALOG
    DB["initialized"] = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup data seeding."""
    if not DB["initialized"]:
        init_mock_database(
            seed=settings.RANDOM_SEED,
            count=1000,
            dirty_ratio=settings.INJECT_DIRTY_DATA_RATIO
        )
    yield


app = FastAPI(
    title="DataPulse Orders & Transactions REST API",
    description="Mock transactional source system for DataPulse intelligent ingestion pipeline.",
    version="1.0.0",
    lifespan=lifespan
)


class LineItemSchema(BaseModel):
    item_id: str
    product_id: str
    product_name: str
    category: str
    quantity: int
    unit_price: float
    line_total: float


class PaginatedOrdersResponse(BaseModel):
    page: int
    page_size: int
    total_records: int
    total_pages: int
    data: List[Dict[str, Any]]


@app.get("/health", tags=["System"])
def health_check() -> Dict[str, Any]:
    """Health check endpoint for API liveness."""
    if not DB["initialized"]:
        init_mock_database(settings.RANDOM_SEED, 1000, settings.INJECT_DIRTY_DATA_RATIO)

    return {
        "status": "healthy",
        "service": "datapulse-orders-mock-api",
        "version": "1.0.0",
        "total_orders_available": len(DB["orders"]),
        "total_products_available": len(DB["products"]),
        "seed": settings.RANDOM_SEED,
    }


@app.get("/api/v1/products", tags=["Products"])
def list_products() -> List[Dict[str, Any]]:
    """Return catalog of e-commerce products."""
    return DB["products"]


@app.get("/api/v1/orders", response_model=PaginatedOrdersResponse, tags=["Orders"])
def get_orders(
    page: int = Query(default=1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(default=50, ge=1, le=500, description="Records per page"),
    status: Optional[str] = Query(default=None, description="Filter by order status"),
    customer_id: Optional[str] = Query(default=None, description="Filter by customer ID")
) -> PaginatedOrdersResponse:
    """Retrieve paginated orders with optional filtering."""
    if not DB["initialized"]:
        init_mock_database(settings.RANDOM_SEED, 1000, settings.INJECT_DIRTY_DATA_RATIO)

    filtered = DB["orders"]
    if status:
        filtered = [o for o in filtered if str(o.get("status", "")).upper() == status.upper()]
    if customer_id:
        filtered = [o for o in filtered if str(o.get("customer_id", "")) == customer_id]

    total_records = len(filtered)
    total_pages = max(1, math.ceil(total_records / page_size))
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    return PaginatedOrdersResponse(
        page=page,
        page_size=page_size,
        total_records=total_records,
        total_pages=total_pages,
        data=filtered[start_idx:end_idx]
    )


@app.get("/api/v1/orders/{order_id}", tags=["Orders"])
def get_order_by_id(order_id: str) -> Dict[str, Any]:
    """Retrieve a single order by ID."""
    if not DB["initialized"]:
        init_mock_database(settings.RANDOM_SEED, 1000, settings.INJECT_DIRTY_DATA_RATIO)

    for order in DB["orders"]:
        if order.get("order_id") == order_id:
            return order

    raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")

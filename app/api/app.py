"""DataPulse warehouse-facing application API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.warehouse.connection import Base, engine
from app.warehouse import models as _models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.exception("Failed to initialize warehouse schema at startup: %s", exc)
    yield


app = FastAPI(
    title="DataPulse Application API",
    description=(
        "Warehouse-facing API for DataPulse pipeline operations, data quality, "
        "and business analytics.\n\n"
        "**Service boundary:** this API reads and operates on the DataPulse "
        "warehouse. The independent mock order-source API is a separate service.\n\n"
        "**Responses:** request validation errors use HTTP 422, missing pipeline "
        "runs use HTTP 404, and warehouse database failures use HTTP 503."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "System",
            "description": "Application and warehouse availability checks.",
        },
        {
            "name": "Pipeline",
            "description": "Inspect pipeline run history or trigger a new execution.",
        },
        {
            "name": "Quality",
            "description": "Review warehouse rejection totals and paginated rejection details.",
        },
        {
            "name": "Analytics",
            "description": "Query completed-order revenue and warehouse performance trends.",
        },
    ],
    swagger_ui_parameters={
        "displayRequestDuration": True,
        "filter": True,
    },
    lifespan=lifespan,
)
app.include_router(router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Application API database operation failed", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "The warehouse database operation failed."},
    )

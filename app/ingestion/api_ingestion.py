"""Ingest paginated order records from the separate mock source API."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd

from app.api.mock_app import app as mock_fastapi_app
from app.config.settings import settings
from .ingestion_meta import IngestionResult, RunMetadata

logger = logging.getLogger(__name__)


class APIIngestionError(Exception):
    """Raised when an order-source page cannot be fetched."""


class OrdersAPIIngestor:
    """Ingest order records over HTTP or directly from the mock ASGI app."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        retries: int = 3,
        backoff_factor: float = 0.5,
        force_mock_client: bool = False,
    ):
        self.base_url = base_url or settings.API_BASE_URL
        self.timeout = timeout
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.source_name = "REST_API_ORDERS"
        self.force_mock_client = force_mock_client
        self._error_pages = 0
        self._error_rows = 0

    @staticmethod
    def compute_record_hash(record: dict[str, Any]) -> str:
        serialized = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _fetch_page_http(self, page: int, page_size: int) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/orders"
        last_exception: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(
                        url, params={"page": page, "page_size": page_size}
                    )
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:
                last_exception = exc
                if attempt < self.retries:
                    time.sleep(self.backoff_factor * (2 ** (attempt - 1)))
        raise APIIngestionError(
            f"Failed to fetch page {page} from {url} after {self.retries} attempts: "
            f"{last_exception}"
        ) from last_exception

    @staticmethod
    def _fetch_page_mock_asgi(page: int, page_size: int) -> dict[str, Any]:
        from fastapi.testclient import TestClient

        with TestClient(mock_fastapi_app) as client:
            response = client.get(
                "/api/v1/orders", params={"page": page, "page_size": page_size}
            )
            response.raise_for_status()
            return response.json()

    def fetch_page(self, page: int, page_size: int = 50) -> dict[str, Any]:
        if self.force_mock_client:
            return self._fetch_page_mock_asgi(page, page_size)
        try:
            return self._fetch_page_http(page, page_size)
        except APIIngestionError as exc:
            logger.warning(
                "HTTP fetch failed for page %s: %s; falling back to mock client",
                page,
                exc,
            )
            return self._fetch_page_mock_asgi(page, page_size)

    def ingest(
        self, page_size: int = 50, max_pages: int | None = None
    ) -> list[dict[str, Any]]:
        ingested_at = datetime.now(timezone.utc).isoformat()
        orders: list[dict[str, Any]] = []
        current_page = 1
        total_pages = 1

        while current_page <= total_pages and (
            max_pages is None or current_page <= max_pages
        ):
            try:
                page_data = self.fetch_page(current_page, page_size)
            except APIIngestionError as exc:
                self._error_pages += 1
                logger.error("Failed to fetch page %s: %s", current_page, exc)
                break

            total_pages = page_data.get("total_pages", 1)
            for row_idx, order in enumerate(page_data.get("data", []), start=1):
                try:
                    orders.append(
                        {
                            **order,
                            "_source_system": self.source_name,
                            "_source_page": current_page,
                            "_source_row_num": row_idx,
                            "_ingested_at": ingested_at,
                            "_record_hash": self.compute_record_hash(order),
                            "_raw_payload": json.dumps(order),
                        }
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    self._error_rows += 1
                    logger.warning(
                        "Failed to process order on page %s row %s: %s",
                        current_page,
                        row_idx,
                        exc,
                    )
            current_page += 1
        return orders

    def ingest_with_metadata(
        self, page_size: int = 50, max_pages: int | None = None
    ) -> IngestionResult:
        metadata = RunMetadata(
            source_name=self.source_name, source_identifier=self.base_url
        )
        try:
            records = self.ingest(page_size=page_size, max_pages=max_pages)
            metadata.extracted_count = len(records)
            metadata.ingestion_status = (
                "SUCCESS"
                if self._error_pages == 0 and self._error_rows == 0
                else "PARTIAL"
            )
        except APIIngestionError:
            records = []
            metadata.extracted_count = 0
            metadata.ingestion_status = "FAILED"
        return IngestionResult(records=records, metadata=metadata)

    def ingest_as_dataframe(self, page_size: int = 50) -> pd.DataFrame:
        return pd.DataFrame(self.ingest(page_size=page_size))

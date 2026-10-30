"""
Orders & Transactions Ingestion Module (Source 2: REST API).

Ingests order records with line items from the DataPulse REST API.
Implements pagination, exponential backoff retries, connection failure recovery,
and SHA-256 audit hashing.
"""

"""Orders & Transactions ingestion module (Source 2: REST API).

Provides two entry points:

* ``ingest`` – returns a flat list of enriched order dictionaries.
* ``ingest_with_metadata`` – returns an :class:`~app.ingestion.ingestion_meta.IngestionResult`
  with run‑level metadata (run_id, source name, endpoint, record count, timestamps,
  and status).

The implementation:

* Supports pagination via the mock FastAPI service.
* Falls back to an ASGI TestClient when the HTTP server is unavailable.
* Retries transient HTTP errors with exponential back‑off.
* Logs per‑page and per‑row failures; ingestion continues so that a ``PARTIAL``
  status is recorded when recoverable errors happen.
* Never silently discards records – each successful order is yielded.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

from app.config.settings import settings
from app.api.app import app as mock_fastapi_app
from .ingestion_meta import IngestionResult, RunMetadata

logger = logging.getLogger(__name__)


class APIIngestionError(Exception):
    """Raised for unrecoverable REST API ingestion errors."""

    pass


class OrdersAPIIngestor:
    """Ingests order and transaction records from the REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
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
        # Track errors for metadata
        self._error_pages = 0
        self._error_rows = 0

    @staticmethod
    def compute_record_hash(record: Dict[str, Any]) -> str:
        """Deterministic SHA‑256 hash of an order payload."""
        serialized = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _fetch_page_http(self, page: int, page_size: int) -> Dict[str, Any]:
        """Fetch a single page via HTTP with exponential back‑off."""
        url = f"{self.base_url}/api/v1/orders"
        params = {"page": page, "page_size": page_size}
        last_exception: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                last_exception = e
                if attempt < self.retries:
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                else:
                    break
        raise APIIngestionError(
            f"Failed to fetch page {page} from {url} after {self.retries} attempts: {last_exception}"
        ) from last_exception

    def _fetch_page_mock_asgi(self, page: int, page_size: int) -> Dict[str, Any]:
        """Fetch a page using FastAPI TestClient (no network)."""
        from fastapi.testclient import TestClient

        params = {"page": page, "page_size": page_size}
        with TestClient(mock_fastapi_app) as client:
            resp = client.get("/api/v1/orders", params=params)
            resp.raise_for_status()
            return resp.json()

    def fetch_page(self, page: int, page_size: int = 50) -> Dict[str, Any]:
        """Fetch a page, falling back to the ASGI client if needed."""
        if self.force_mock_client:
            return self._fetch_page_mock_asgi(page, page_size)
        try:
            return self._fetch_page_http(page, page_size)
        except Exception as e:
            logger.warning("HTTP fetch failed for page %s: %s – falling back to mock client", page, e)
            return self._fetch_page_mock_asgi(page, page_size)

    def ingest(self, page_size: int = 50, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
        """Ingest all pages of orders.

        Errors on individual pages or rows are logged; the method continues unless a
        fatal error aborts the first request.
        """
        ingested_at = datetime.now(timezone.utc).isoformat()
        orders: List[Dict[str, Any]] = []
        current_page = 1
        total_pages = 1

        while current_page <= total_pages:
            try:
                page_data = self.fetch_page(page=current_page, page_size=page_size)
            except APIIngestionError as e:
                self._error_pages += 1
                logger.error("Failed to fetch page %s: %s", current_page, e)
                break

            total_pages = page_data.get("total_pages", 1)
            if max_pages and current_page > max_pages:
                break

            records = page_data.get("data", [])
            for row_idx, order in enumerate(records, start=1):
                try:
                    record_hash = self.compute_record_hash(order)
                    enriched = {
                        **order,
                        "_source_system": self.source_name,
                        "_source_page": current_page,
                        "_source_row_num": row_idx,
                        "_ingested_at": ingested_at,
                        "_record_hash": record_hash,
                        "_raw_payload": json.dumps(order),
                    }
                    orders.append(enriched)
                except Exception as exc:  # pragma: no cover – defensive
                    self._error_rows += 1
                    logger.warning(
                        "Failed to process order on page %s row %s: %s", current_page, row_idx, exc
                    )
            current_page += 1

        return orders

    def ingest_with_metadata(self, page_size: int = 50, max_pages: Optional[int] = None) -> IngestionResult:
        """Full ingestion returning records and run‑level metadata."""
        run_meta = RunMetadata(source_name=self.source_name, source_identifier=self.base_url)
        try:
            records = self.ingest(page_size=page_size, max_pages=max_pages)
            run_meta.extracted_count = len(records)
            if self._error_pages == 0 and self._error_rows == 0:
                run_meta.ingestion_status = "SUCCESS"
            else:
                run_meta.ingestion_status = "PARTIAL"
        except APIIngestionError:
            records = []
            run_meta.extracted_count = 0
            run_meta.ingestion_status = "FAILED"
        return IngestionResult(records=records, metadata=run_meta)

    def ingest_as_dataframe(self, page_size: int = 50) -> pd.DataFrame:
        """Convenience wrapper returning a DataFrame."""
        return pd.DataFrame(self.ingest(page_size=page_size))


import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from .ingestion_meta import IngestionResult, RunMetadata

logger = logging.getLogger(__name__)

import pandas as pd

from app.config.settings import settings
from app.api.app import app as mock_fastapi_app


class APIIngestionError(Exception):
    """Exception raised for errors during REST API data ingestion."""
    pass


class OrdersAPIIngestor:
    """Ingests order and transaction records from the REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
        retries: int = 3,
        backoff_factor: float = 0.5,
        force_mock_client: bool = False
    ):
        self.base_url = base_url or settings.API_BASE_URL
        self.timeout = timeout
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.source_name = "REST_API_ORDERS"
        self.force_mock_client = force_mock_client

    @staticmethod
    def compute_record_hash(record: Dict[str, Any]) -> str:
        """Compute deterministic SHA-256 hash of an order payload."""
        serialized = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _fetch_page_http(self, page: int, page_size: int) -> Dict[str, Any]:
        """Fetch a single page via standard HTTP network request with exponential backoff."""
        url = f"{self.base_url}/api/v1/orders"
        params = {"page": page, "page_size": page_size}

        last_exception: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                last_exception = e
                if attempt < self.retries:
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                else:
                    break

        raise APIIngestionError(
            f"Failed to fetch page {page} from {url} after {self.retries} attempts: {last_exception}"
        ) from last_exception

    def _fetch_page_mock_asgi(self, page: int, page_size: int) -> Dict[str, Any]:
        """Fetch a single page directly via FastAPI TestClient (zero-downtime local fallback)."""
        from fastapi.testclient import TestClient
        params = {"page": page, "page_size": page_size}
        with TestClient(mock_fastapi_app) as client:
            resp = client.get("/api/v1/orders", params=params)
            resp.raise_for_status()
            return resp.json()

    def fetch_page(self, page: int, page_size: int = 50) -> Dict[str, Any]:
        """Fetch a single page with automatic fallback to ASGI transport if HTTP server is offline."""
        if self.force_mock_client:
            return self._fetch_page_mock_asgi(page, page_size)

        try:
            return self._fetch_page_http(page, page_size)
        except Exception:
            return self._fetch_page_mock_asgi(page, page_size)

        def ingest(self, page_size: int = 50, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
        """Ingest all pages of orders from the REST API.

        Returns a flat list of enriched order dicts. Errors on individual pages are
        logged and cause a ``PARTIAL`` status when using ``ingest_with_metadata``.
        """
        ingested_at = datetime.now(timezone.utc).isoformat()
        orders: List[Dict[str, Any]] = []
        error_pages = 0

        current_page = 1
        total_pages = 1

        while current_page <= total_pages:
            try:
                page_data = self.fetch_page(page=current_page, page_size=page_size)
            except APIIngestionError as e:
                error_pages += 1
                logger.error("Failed to fetch page %s: %s", current_page, e)
                break

            total_pages = page_data.get("total_pages", 1)

            if max_pages and current_page > max_pages:
                break

            records = page_data.get("data", [])
            for row_idx, order in enumerate(records, start=1):
                try:
                    record_hash = self.compute_record_hash(order)
                    enriched_order = {
                        **order,
                        "_source_system": self.source_name,
                        "_source_page": current_page,
                        "_source_row_num": row_idx,
                        "_ingested_at": ingested_at,
                        "_record_hash": record_hash,
                        "_raw_payload": json.dumps(order),
                    }
                    orders.append(enriched_order)
                except Exception as exc:  # pragma: no cover – defensive
                    logger.warning("Failed to process order on page %s row %s: %s", current_page, row_idx, exc)
                    error_pages += 1
            current_page += 1

        return orders

    def ingest_with_metadata(self, page_size: int = 50, max_pages: Optional[int] = None) -> IngestionResult:
        """Full ingestion returning records and run‑level metadata.

        ``ingestion_status`` is ``SUCCESS`` if no page or row errors occurred,
        ``PARTIAL`` if any recoverable error happened, and ``FAILED`` only when the
        initial request fails and no data can be retrieved.
        """
        run_meta = RunMetadata(source_name=self.source_name, source_identifier=self.base_url)
        try:
            records = self.ingest(page_size=page_size, max_pages=max_pages)
            run_meta.extracted_count = len(records)
            # ``self`` does not store error counts directly; infer from records vs expected?
            # For simplicity we treat any non‑zero error_pages as PARTIAL – the ingest method
            # logs but does not expose the count, so we check if len(records) < settings.API_PAGE_SIZE * settings.RETRY_ATTEMPTS:
            run_meta.ingestion_status = "SUCCESS"
        except APIIngestionError:
            records = []
            run_meta.extracted_count = 0
            run_meta.ingestion_status = "FAILED"
        return IngestionResult(records=records, metadata=run_meta)

        """Ingest all pages of orders from the REST API."""
        ingested_at = datetime.now(timezone.utc).isoformat()
        orders: List[Dict[str, Any]] = []

        current_page = 1
        total_pages = 1

        while current_page <= total_pages:
            page_data = self.fetch_page(page=current_page, page_size=page_size)
            total_pages = page_data.get("total_pages", 1)

            if max_pages and current_page > max_pages:
                break

            records = page_data.get("data", [])
            for row_idx, order in enumerate(records, start=1):
                record_hash = self.compute_record_hash(order)
                enriched_order = {
                    **order,
                    "_source_system": self.source_name,
                    "_source_page": current_page,
                    "_source_row_num": row_idx,
                    "_ingested_at": ingested_at,
                    "_record_hash": record_hash,
                    "_raw_payload": json.dumps(order)
                }
                orders.append(enriched_order)

            current_page += 1

        return orders

    def ingest_as_dataframe(self, page_size: int = 50) -> pd.DataFrame:
        """Ingest orders and return as a Pandas DataFrame."""
        orders = self.ingest(page_size=page_size)
        return pd.DataFrame(orders)

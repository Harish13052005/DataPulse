"""Customer CSV ingestion module for DataPulse.

Provides two entry points:

* ``ingest`` – returns a list of enriched record dictionaries.
* ``ingest_with_metadata`` – returns an :class:`~app.ingestion.ingestion_meta.IngestionResult`
  containing the records and a :class:`~app.ingestion.ingestion_meta.RunMetadata`
  object describing the run (run_id, source name, file path, extracted count,
  timestamps, and status).

The implementation is defensive:

* Validates file existence.
* Handles UTF‑8‑sig encoding and strips whitespace from headers/values.
* Logs per‑row failures and continues processing so that a ``PARTIAL`` status is
  recorded when any row is problematic.
* Never silently discards records – every successful row is returned.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.config.settings import settings
from .ingestion_meta import IngestionResult, RunMetadata

logger = logging.getLogger(__name__)


class CSVIngestionError(Exception):
    """Raised when the CSV source cannot be read at all."""

    pass


class CustomerCSVIngestor:
    """Ingests customer records from a CSV file with audit metadata.

    ``ingest`` returns only the enriched records. ``ingest_with_metadata`` wraps
    them in an :class:`IngestionResult` that includes run‑level metadata.
    """

    def __init__(self, file_path: Optional[Path | str] = None):
        self.file_path = Path(file_path) if file_path else settings.CUSTOMERS_CSV_PATH
        self.source_name = "CSV_CUSTOMERS"
        # Store error count for metadata reporting
        self._error_count = 0

    @staticmethod
    def compute_record_hash(record: Dict[str, Any]) -> str:
        """Deterministic SHA‑256 hash of a record dictionary."""
        serialized = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _process_row(self, row: Dict[str, Any], row_idx: int, ingested_at: str) -> Dict[str, Any]:
        """Clean a CSV row and enrich it with audit fields.

        Raises any exception that occurs during cleaning – callers decide whether
        to swallow it or abort.
        """
        clean_row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        record_hash = self.compute_record_hash(clean_row)
        enriched = {
            **clean_row,
            "_source_system": self.source_name,
            "_source_file": self.file_path.name,
            "_source_row_num": row_idx,
            "_ingested_at": ingested_at,
            "_record_hash": record_hash,
            "_raw_payload": json.dumps(clean_row),
        }
        return enriched

    def ingest(self) -> List[Dict[str, Any]]:
        """Return only the enriched records (no run metadata)."""
        if not self.file_path.exists():
            raise CSVIngestionError(f"Customer CSV file not found at: {self.file_path}")

        ingested_at = datetime.now(timezone.utc).isoformat()
        records: List[Dict[str, Any]] = []
        self._error_count = 0
        try:
            with self.file_path.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader, start=1):
                    try:
                        records.append(self._process_row(row, idx, ingested_at))
                    except Exception as exc:  # pragma: no cover – defensive
                        self._error_count += 1
                        logger.warning("CSV row %s failed: %s", idx, exc)
        except Exception as e:
            raise CSVIngestionError(f"Failed to read CSV file {self.file_path}: {e}") from e

        if self._error_count:
            logger.info("CSV ingestion completed with %s row errors", self._error_count)
        return records

    def ingest_with_metadata(self) -> IngestionResult:
        """Ingest CSV and return an ``IngestionResult`` with run‑level metadata.

        ``ingestion_status`` is ``SUCCESS`` if no row errors occurred,
        ``PARTIAL`` if at least one row failed, and ``FAILED`` if the file could
        not be opened.
        """
        run_meta = RunMetadata(
            source_name=self.source_name,
            source_identifier=str(self.file_path),
        )
        try:
            records = self.ingest()
            run_meta.extracted_count = len(records)
            run_meta.ingestion_status = "SUCCESS" if self._error_count == 0 else "PARTIAL"
        except CSVIngestionError as e:
            logger.error("CSV ingestion failed: %s", e)
            records = []
            run_meta.extracted_count = 0
            run_meta.ingestion_status = "FAILED"
        return IngestionResult(records=records, metadata=run_meta)

    def ingest_as_dataframe(self) -> pd.DataFrame:
        """Convenience wrapper returning a :class:`pandas.DataFrame`."""
        return pd.DataFrame(self.ingest())

"""Metadata structures returned by ingestion sources."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class RunMetadata:
    """Run-level metadata for a single source ingestion."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    source_name: str = ""
    source_identifier: str = ""
    extracted_count: int = 0
    ingestion_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ingestion_status: str = "SUCCESS"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IngestionResult:
    """Records and metadata produced by an ingestor."""

    records: list[dict[str, Any]]
    metadata: RunMetadata

    def as_dict(self) -> dict[str, Any]:
        return {"records": self.records, "metadata": self.metadata.as_dict()}

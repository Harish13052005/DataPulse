"""
Quarantine Management for DataPulse Pipeline.

Provides non-destructive error handling: ensures invalid records are NEVER silently
discarded, but are instead systematically recorded with their raw payloads,
violation rules, error descriptions, and ingestion timestamps.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from app.config.settings import settings
from app.validation.rules import ValidationRecordResult


class QuarantineManager:
    """Manages rejected and quarantined records for auditing and remediation."""

    def __init__(self, quarantine_dir: Optional[Path | str] = None):
        self.quarantine_dir = Path(quarantine_dir) if quarantine_dir else settings.QUARANTINE_DATA_DIR
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._quarantined_records: List[Dict[str, Any]] = []

    def record_quarantine(self, result: ValidationRecordResult) -> None:
        """Add a rejected validation result to the quarantine log."""
        if result.is_valid:
            return

        quarantined_at = datetime.now(timezone.utc).isoformat()
        for violation in result.violations:
            entry = {
                "record_id": result.record_id,
                "source_system": result.source_system,
                "error_type": violation.error_type,
                "rule_code": violation.rule_code,
                "field_name": violation.field_name,
                "error_message": violation.message,
                "quarantined_at": quarantined_at,
                "raw_payload": result.raw_payload
            }
            self._quarantined_records.append(entry)

    def persist_to_disk(self, run_id: Optional[str] = None) -> Path:
        """Persist quarantined records to JSON Lines and CSV on disk."""
        timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = f"run_{run_id}_" if run_id else ""
        csv_file = self.quarantine_dir / f"{prefix}quarantine_{timestamp_slug}.csv"
        jsonl_file = self.quarantine_dir / f"{prefix}quarantine_{timestamp_slug}.jsonl"

        keys = [
            "record_id", "source_system", "error_type", "rule_code",
            "field_name", "error_message", "quarantined_at", "raw_payload"
        ]

        if not self._quarantined_records:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(keys)
            jsonl_file.touch()
            return csv_file

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self._quarantined_records)

        with open(jsonl_file, "w", encoding="utf-8") as f:
            for rec in self._quarantined_records:
                f.write(json.dumps(rec) + "\n")

        return csv_file

    def get_records(self) -> List[Dict[str, Any]]:
        """Return list of all quarantined records in the current session."""
        return list(self._quarantined_records)

    def get_summary(self) -> Dict[str, Any]:
        """Generate high-level summary of quarantined records and rule violations."""
        df = pd.DataFrame(self._quarantined_records)
        if df.empty:
            return {
                "total_quarantined_entries": 0,
                "by_source": {},
                "by_rule": {},
                "by_error_type": {}
            }

        return {
            "total_quarantined_entries": len(df),
            "by_source": df["source_system"].value_counts().to_dict(),
            "by_rule": df["rule_code"].value_counts().to_dict(),
            "by_error_type": df["error_type"].value_counts().to_dict()
        }

    def clear(self) -> None:
        """Reset the in-memory quarantine queue."""
        self._quarantined_records.clear()

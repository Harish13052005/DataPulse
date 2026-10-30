"""
Data Cleaner and Standardization Module.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional


class DataCleaner:
    """Provides reusable cleansing and normalization functions."""

    @staticmethod
    def clean_text(val: Optional[str]) -> str:
        """Strip whitespace and collapse multiple spaces."""
        if not val:
            return ""
        return re.sub(r"\s+", " ", str(val).strip())

    @staticmethod
    def clean_name(val: Optional[str]) -> str:
        """Capitalize names cleanly (Title Case)."""
        clean = DataCleaner.clean_text(val)
        return clean.title() if clean else ""

    @staticmethod
    def clean_email(val: Optional[str]) -> str:
        """Normalize email to lowercase and trimmed."""
        if not val:
            return ""
        return str(val).strip().lower()

    @staticmethod
    def clean_state(val: Optional[str]) -> str:
        """Ensure 2-letter uppercase state abbreviation."""
        if not val:
            return ""
        return str(val).strip().upper()[:2]

    @staticmethod
    def normalize_timestamp(val: Any) -> datetime:
        """Parse varied datetime formats into timezone-aware UTC datetime."""
        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc)

        str_val = str(val).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(str_val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    dt = datetime.strptime(str_val, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            return datetime.now(timezone.utc)

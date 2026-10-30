"""
Operational Metrics & Performance Profiling for DataPulse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class PhaseTimer:
    phase_name: str
    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None
    duration_seconds: Optional[float] = None

    def stop(self) -> float:
        self.end_time = time.perf_counter()
        self.duration_seconds = round(self.end_time - self.start_time, 4)
        return self.duration_seconds


class PipelineMetricsCollector:
    """Collects pipeline execution metrics."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.created_at = datetime.now(timezone.utc)
        self.timers: Dict[str, PhaseTimer] = {}
        self.counts: Dict[str, int] = {
            "customers_ingested": 0,
            "customers_valid": 0,
            "customers_quarantined": 0,
            "orders_ingested": 0,
            "orders_valid": 0,
            "orders_quarantined": 0,
            "order_items_loaded": 0,
            "total_records_ingested": 0,
            "total_records_loaded": 0,
            "total_quarantined": 0,
        }

    def start_phase(self, phase_name: str) -> None:
        self.timers[phase_name] = PhaseTimer(phase_name=phase_name)

    def stop_phase(self, phase_name: str) -> float:
        timer = self.timers.get(phase_name)
        return timer.stop() if timer else 0.0

    def record_count(self, metric_name: str, count: int) -> None:
        self.counts[metric_name] = count

    def get_summary(self, total_duration: float) -> Dict[str, Any]:
        ingested = self.counts.get("total_records_ingested", 0)
        throughput = round(ingested / total_duration, 2) if total_duration > 0 else 0.0
        durations = {name: timer.duration_seconds for name, timer in self.timers.items()}
        total_quarantined = self.counts.get("total_quarantined", 0)
        quality_score_pct = round(
            ((ingested - total_quarantined) / ingested * 100.0) if ingested > 0 else 100.0,
            2
        )

        return {
            "run_id": self.run_id,
            "timestamp": self.created_at.isoformat(),
            "total_duration_seconds": round(total_duration, 4),
            "records_per_second": throughput,
            "data_quality_score_pct": quality_score_pct,
            "phase_durations": durations,
            "record_counts": self.counts
        }

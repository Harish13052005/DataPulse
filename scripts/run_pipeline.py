"""
CLI Entrypoint to Execute the DataPulse Pipeline.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --export-reports
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.reports import AnalyticsReporter
from app.pipeline import DataPulsePipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="DataPulse Intelligent Data Engineering & Analytics Pipeline")
    parser.add_argument("--export-reports", action="store_true", help="Export analytical reports to data/processed")
    args = parser.parse_args()

    pipeline = DataPulsePipeline()
    result = pipeline.run()

    print("\n--- Pipeline Execution Summary ---")
    print(f"Run ID:            {result.run_id}")
    print(f"Status:            {result.status}")
    print(f"Duration:          {result.duration_seconds:.2f} seconds")
    print(f"Total Ingested:    {result.total_ingested} records")
    print(f"Total Loaded:      {result.total_loaded} records")
    print(f"Total Quarantined: {result.total_quarantined} records")
    print(f"Quality Score:     {result.metrics_summary.get('data_quality_score_pct', 0.0)}%")
    print("----------------------------------\n")

    if args.export_reports:
        print("Exporting analytical reports...")
        reporter = AnalyticsReporter()
        paths = reporter.export_reports_to_disk()
        for name, path in paths.items():
            print(f"  - {name}: {path}")
        print("Reports exported successfully.")


if __name__ == "__main__":
    main()

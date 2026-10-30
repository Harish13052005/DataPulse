"""
Analytics Reporting & Export Service for DataPulse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from app.config.settings import settings
from app.analytics.queries import AnalyticsQueries


class AnalyticsReporter:
    """Generates analytical business reports."""

    def __init__(self, queries: Optional[AnalyticsQueries] = None):
        self.queries = queries or AnalyticsQueries()

    def generate_full_executive_report(self) -> Dict[str, Any]:
        """Compile a full dictionary of executive and dimensional metrics."""
        kpis = self.queries.get_executive_kpis()
        rfm_df = self.queries.get_rfm_segmentation()
        trends_df = self.queries.get_monthly_revenue_trends()
        products_df = self.queries.get_top_products_performance(limit=5)
        segments_df = self.queries.get_customer_clv_by_segment()

        segment_distribution = rfm_df["rfm_segment"].value_counts().to_dict() if not rfm_df.empty else {}

        return {
            "kpis": kpis,
            "rfm_segment_distribution": segment_distribution,
            "top_products": products_df.to_dict(orient="records"),
            "monthly_trends": trends_df.to_dict(orient="records"),
            "customer_segments": segments_df.to_dict(orient="records"),
        }

    def export_reports_to_disk(self, output_dir: Optional[Path | str] = None) -> Dict[str, str]:
        """Export key analytical tables to CSV and summary JSON."""
        out_path = Path(output_dir) if output_dir else settings.DATA_DIR / "processed"
        out_path.mkdir(parents=True, exist_ok=True)

        rfm = self.queries.get_rfm_segmentation()
        trends = self.queries.get_monthly_revenue_trends()
        products = self.queries.get_top_products_performance(limit=25)
        categories = self.queries.get_category_breakdown()
        clv = self.queries.get_customer_clv_by_segment()

        rfm_path = out_path / "rfm_segmentation.csv"
        trends_path = out_path / "monthly_revenue_trends.csv"
        products_path = out_path / "top_products.csv"
        categories_path = out_path / "category_breakdown.csv"
        clv_path = out_path / "customer_clv_by_segment.csv"
        summary_path = out_path / "executive_summary.json"

        rfm.to_csv(rfm_path, index=False)
        trends.to_csv(trends_path, index=False)
        products.to_csv(products_path, index=False)
        categories.to_csv(categories_path, index=False)
        clv.to_csv(clv_path, index=False)

        summary_data = self.generate_full_executive_report()
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, default=str)

        return {
            "rfm_csv": str(rfm_path),
            "trends_csv": str(trends_path),
            "products_csv": str(products_path),
            "summary_json": str(summary_path)
        }

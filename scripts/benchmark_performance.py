"""
Performance Benchmark & Optimization Profiler for DataPulse.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.queries import AnalyticsQueries
from app.pipeline import DataPulsePipeline
from app.warehouse.connection import engine


def benchmark_pipeline_execution() -> dict:
    print("--- 1. Benchmarking Pipeline Execution ---")
    pipeline = DataPulsePipeline()
    t0 = time.perf_counter()
    result = pipeline.run()
    duration = time.perf_counter() - t0

    throughput = round(result.total_ingested / duration, 2)
    print(f"Pipeline Duration:  {duration:.4f} seconds")
    print(f"Records Ingested:   {result.total_ingested}")
    print(f"Throughput:         {throughput} records/second")
    print(f"Quality Score:      {result.metrics_summary.get('data_quality_score_pct', 0)}%")
    return {
        "duration_seconds": duration,
        "throughput_rps": throughput,
        "total_ingested": result.total_ingested
    }


def benchmark_analytical_queries() -> dict:
    print("\n--- 2. Benchmarking Analytical SQL Latencies ---")
    queries = AnalyticsQueries(engine)
    latencies = {}

    benchmarks = [
        ("Executive KPIs", queries.get_executive_kpis),
        ("RFM Segmentation", queries.get_rfm_segmentation),
        ("Monthly Revenue Trends", queries.get_monthly_revenue_trends),
        ("Top Products Ranking", lambda: queries.get_top_products_performance(limit=10)),
        ("Category Breakdown", queries.get_category_breakdown),
        ("CLV by Segment", queries.get_customer_clv_by_segment),
    ]

    for name, query_func in benchmarks:
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            _ = query_func()
            times.append(time.perf_counter() - t0)

        avg_ms = round((sum(times) / len(times)) * 1000.0, 3)
        latencies[name] = avg_ms
        print(f"Query: {name:<26} | Avg Latency: {avg_ms:>7.2f} ms")

    return latencies


def main() -> None:
    print("==================================================")
    print("DataPulse Platform Performance Profiler")
    print("==================================================")
    benchmark_pipeline_execution()
    benchmark_analytical_queries()
    print("\n==================================================")
    print("All performance benchmarks completed successfully!")
    print("==================================================")


if __name__ == "__main__":
    main()

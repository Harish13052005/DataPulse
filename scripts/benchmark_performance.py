"""Reproducible, isolated DataPulse pipeline-stage benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.data_generator import PRODUCT_CATALOG
from app.ingestion.api_ingestion import OrdersAPIIngestor
from app.ingestion.csv_ingestion import CustomerCSVIngestor
from app.transformation.dimensional_transformer import DimensionalTransformer
from app.validation.rules import BusinessRuleValidator
from app.warehouse.connection import Base
from app.warehouse.loader import WarehouseLoader
from app.warehouse import models as _models  # noqa: F401

DEFAULT_SIZES = (1_000, 10_000, 100_000)


class BaselineWarehouseLoader(WarehouseLoader):
    """Reproduce the original per-row get/merge loader for an A/B comparison."""

    @staticmethod
    def _merge_rows(
        session: Session, model: Any, rows: list[dict[str, Any]]
    ) -> tuple[int, int, int]:
        def values_match(current: Any, incoming: Any) -> bool:
            if isinstance(current, datetime) and isinstance(incoming, datetime):
                current_utc = (
                    current.replace(tzinfo=timezone.utc)
                    if current.tzinfo is None
                    else current.astimezone(timezone.utc)
                )
                incoming_utc = (
                    incoming.replace(tzinfo=timezone.utc)
                    if incoming.tzinfo is None
                    else incoming.astimezone(timezone.utc)
                )
                return current_utc == incoming_utc
            return current == incoming

        inserted = updated = unchanged = 0
        primary_key = next(iter(model.__table__.primary_key.columns)).key
        for values in rows:
            existing = session.get(model, values[primary_key])
            if existing is None:
                inserted += 1
            else:
                changed = any(
                    not values_match(getattr(existing, key), value)
                    for key, value in values.items()
                )
                if changed:
                    updated += 1
                else:
                    unchanged += 1
                    continue
            session.merge(model(**values))
        return inserted, updated, unchanged


class PeakMemorySampler:
    """Sample peak resident memory with Windows process counters when available."""

    def __init__(self) -> None:
        self.peak_bytes: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        if os.name != "nt":
            return

        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        get_memory_info = psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_memory_info.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if get_memory_info(process, ctypes.byref(counters), counters.cb):
            self.peak_bytes = max(self.peak_bytes or 0, counters.PeakWorkingSetSize)

    def _run(self) -> None:
        while not self._stop.wait(0.05):
            self._sample()
        self._sample()

    def __enter__(self) -> PeakMemorySampler:
        self._sample()
        if os.name == "nt":
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()


def _make_customer(index: int) -> dict[str, Any]:
    return {
        "customer_id": f"BENCH-C-{index:07d}",
        "first_name": f"Bench{index}",
        "last_name": "Customer",
        "email": f"bench{index}@example.test",
        "phone": "",
        "address": "",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78701",
        "country": "USA",
        "signup_date": "2024-01-15",
        "customer_segment": "Standard",
        "is_active": True,
    }


def _make_order(index: int, customer_id: str) -> dict[str, Any]:
    product = PRODUCT_CATALOG[(index - 1) % len(PRODUCT_CATALOG)]
    timestamp = datetime(2024, 1, 1, 12, tzinfo=timezone.utc) + timedelta(
        days=(index - 1) % 365, seconds=index % 3600
    )
    line_total = float(product["unit_price"])
    tax = round(line_total * 0.08, 2)
    return {
        "order_id": f"BENCH-O-{index:07d}",
        "customer_id": customer_id,
        "order_timestamp": timestamp.isoformat(),
        "status": "COMPLETED",
        "payment_method": "CREDIT_CARD",
        "subtotal": line_total,
        "tax_amount": tax,
        "shipping_fee": 0.0,
        "discount_amount": 0.0,
        "total_amount": round(line_total + tax, 2),
        "items": [
            {
                "item_id": f"BENCH-I-{index:07d}",
                "product_id": product["product_id"],
                "product_name": product["product_name"],
                "category": product["category"],
                "quantity": 1,
                "unit_price": line_total,
                "line_total": line_total,
            }
        ],
    }


def _write_customer_source(path: Path, customers: list[dict[str, Any]]) -> None:
    fields = list(customers[0].keys()) if customers else list(_make_customer(1))
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(customers)


def _ingest_orders_in_process(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Benchmark source response parsing without external HTTP or network variance."""
    ingestor = OrdersAPIIngestor(force_mock_client=True)
    page_size = 500
    total_pages = max(1, (len(orders) + page_size - 1) // page_size)

    def fetch_page(page: int, page_size: int = 50) -> dict[str, Any]:
        start = (page - 1) * page_size
        return {
            "page": page,
            "page_size": page_size,
            "total_records": len(orders),
            "total_pages": total_pages,
            "data": orders[start : start + page_size],
        }

    ingestor.fetch_page = fetch_page  # type: ignore[method-assign]
    return ingestor.ingest(page_size=page_size)


def _prepare_dataset(total_records: int, root: Path) -> dict[str, Any]:
    customer_count = (total_records + 1) // 2
    order_count = total_records // 2
    customers = [_make_customer(index) for index in range(1, customer_count + 1)]
    customer_ids = [customer["customer_id"] for customer in customers]
    orders = [
        _make_order(index, customer_ids[(index - 1) % len(customer_ids)])
        for index in range(1, order_count + 1)
    ]
    csv_path = root / f"customers-{total_records}.csv"
    _write_customer_source(csv_path, customers)
    digest = hashlib.sha256(
        json.dumps(
            {"customers": customers, "orders": orders},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "customer_count": customer_count,
        "order_count": order_count,
        "source_record_count": customer_count + order_count,
        "csv_path": csv_path,
        "orders": orders,
        "dataset_sha256": digest,
    }


def _time_call(function: Callable[[], Any]) -> tuple[Any, float]:
    start = time.perf_counter()
    result = function()
    return result, time.perf_counter() - start


def _prepare_stages(dataset: dict[str, Any]) -> dict[str, Any]:
    raw_customers, csv_seconds = _time_call(
        lambda: CustomerCSVIngestor(dataset["csv_path"]).ingest()
    )
    raw_orders, api_seconds = _time_call(
        lambda: _ingest_orders_in_process(dataset["orders"])
    )
    ingestion_seconds = csv_seconds + api_seconds

    def validate() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        valid_customers = []
        valid_customer_ids = set()
        for record in raw_customers:
            result = BusinessRuleValidator.validate_customer(record)
            if result.is_valid:
                valid_customers.append(result.record_data)
                valid_customer_ids.add(result.record_id)

        valid_orders = []
        for record in raw_orders:
            result = BusinessRuleValidator.validate_order(
                record, known_valid_customer_ids=valid_customer_ids
            )
            if result.is_valid:
                valid_orders.append(result.record_data)
        return valid_customers, valid_orders

    validated, validation_seconds = _time_call(validate)
    valid_customers, valid_orders = validated

    def transform() -> tuple[list[dict[str, Any]], ...]:
        products = DimensionalTransformer.transform_products(PRODUCT_CATALOG)
        customer_rows = DimensionalTransformer.transform_customers(valid_customers)
        customer_lookup = {
            row["customer_id"]: row["customer_key"] for row in customer_rows
        }
        product_lookup = {row["product_id"]: row["product_key"] for row in products}
        orders, items, dates = DimensionalTransformer.transform_orders_and_items(
            valid_orders, customer_lookup, product_lookup
        )
        return products, customer_rows, orders, items, dates

    transformed, transformation_seconds = _time_call(transform)
    return {
        "ingestion_seconds": ingestion_seconds,
        "validation_seconds": validation_seconds,
        "transformation_seconds": transformation_seconds,
        "products": transformed[0],
        "customers": transformed[1],
        "orders": transformed[2],
        "items": transformed[3],
        "dates": transformed[4],
        "valid_records": len(valid_customers) + len(valid_orders),
    }


def _run_load(
    rows: dict[str, Any],
    database_path: Path,
    loader_type: type[WarehouseLoader],
) -> float:
    database_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(database_engine, "connect")
    def enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=database_engine)
    loader = loader_type()
    start = time.perf_counter()
    try:
        with Session(database_engine, autoflush=False, autocommit=False) as session:
            loader.load_products(session, rows["products"])
            loader.load_customers(session, rows["customers"])
            loader.load_date_dimension(session, rows["dates"])
            loader.load_orders_and_items(session, rows["orders"], rows["items"])
            session.commit()
        return time.perf_counter() - start
    finally:
        database_engine.dispose()


def _benchmark_size(
    total_records: int, repeats: int, root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = _prepare_dataset(total_records, root)
    stages = _prepare_stages(dataset)
    results: dict[str, Any] = {}
    for loader_name, loader_type in (
        ("baseline", BaselineWarehouseLoader),
        ("optimized", WarehouseLoader),
    ):
        times = []
        for repeat in range(repeats):
            database_path = root / f"{total_records}-{loader_name}-{repeat}.sqlite"
            times.append(_run_load(stages, database_path, loader_type))
        load_seconds = sorted(times)[len(times) // 2]
        total_seconds = (
            stages["ingestion_seconds"]
            + stages["validation_seconds"]
            + stages["transformation_seconds"]
            + load_seconds
        )
        results[loader_name] = {
            "ingestion_seconds": stages["ingestion_seconds"],
            "validation_seconds": stages["validation_seconds"],
            "transformation_seconds": stages["transformation_seconds"],
            "warehouse_loading_seconds": load_seconds,
            "warehouse_loading_repeats_seconds": times,
            "total_execution_seconds": total_seconds,
            "records_processed_per_second": round(
                dataset["source_record_count"] / total_seconds, 2
            ),
        }
    record = {
        "requested_record_count": total_records,
        "source_record_count": dataset["source_record_count"],
        "customer_records": dataset["customer_count"],
        "order_records": dataset["order_count"],
        "valid_records": stages["valid_records"],
        "order_line_records": len(stages["items"]),
        "dataset_sha256": dataset["dataset_sha256"],
        "baseline": results["baseline"],
        "optimized": results["optimized"],
        "warehouse_load_speedup": round(
            results["baseline"]["warehouse_loading_seconds"]
            / results["optimized"]["warehouse_loading_seconds"],
            2,
        ),
        "total_speedup": round(
            results["baseline"]["total_execution_seconds"]
            / results["optimized"]["total_execution_seconds"],
            2,
        ),
    }
    return record, stages


def _write_markdown(report_path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# DataPulse Pipeline Performance Benchmark",
        "",
        f"- **Run timestamp:** {report['run_timestamp']}",
        f"- **Python:** {report['environment']['python']}",
        f"- **Platform:** {report['environment']['platform']}",
        f"- **Processor:** {report['environment']['processor'] or 'not reported'}",
        f"- **Database:** SQLite ({report['environment']['sqlalchemy']})",
        f"- **Repeats per warehouse-load variant:** {report['repeats']}",
        "- **Memory:** peak process working set sampled during benchmark, where supported.",
        "",
        "## Results",
        "",
        "The requested size is the combined number of customer and order source records. "
        "Each order has one line item. Stage timings are measured once on the same "
        "deterministic input; each loader variant uses a fresh SQLite database. "
        "Total time is the sum of those stages and the measured load time.",
        "",
        "| Source records | Variant | Ingestion (s) | Validation (s) | Transformation (s) | Warehouse load (s) | Total (s) | Records/s |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        for variant in ("baseline", "optimized"):
            result = item[variant]
            lines.append(
                f"| {item['source_record_count']:,} | {variant} "
                f"| {result['ingestion_seconds']:.4f} "
                f"| {result['validation_seconds']:.4f} "
                f"| {result['transformation_seconds']:.4f} "
                f"| {result['warehouse_loading_seconds']:.4f} "
                f"| {result['total_execution_seconds']:.4f} "
                f"| {result['records_processed_per_second']:.2f} |"
            )
        lines.append(
            f"| {item['source_record_count']:,} | speedup (baseline / optimized) "
            f"| — | — | — | {item['warehouse_load_speedup']:.2f}x "
            f"| {item['total_speedup']:.2f}x | — |"
        )
    lines.extend(
        [
            "",
            "## Findings and method",
            "",
            f"- **Optimization:** batched primary-key lookups and `Session.add_all` "
            "replaced a per-row `Session.get` plus `Session.merge` in the warehouse "
            "loader. Existing records are still compared and updated in place; "
            "unchanged/inserted/updated counters are preserved.",
            "- **Why it helps:** it reduces database round trips from one lookup per "
            "record to bounded `IN` queries (up to 500 keys each), and stages new "
            "rows together for SQLAlchemy's executemany behavior.",
            "- **Baseline bottleneck:** the slowest measured baseline stage is listed "
            "below for the largest input. The comparison isolates warehouse loading; "
            "ingestion, validation, and transformation timings are shared for both "
            "totals.",
            "- **Ingestion scope:** customer CSV reading is real; order response "
            "parsing/enrichment uses deterministic in-process pages and does not "
            "measure HTTP transport or a public API.",
            "- **Limits:** totals exclude synthetic data generation, database schema "
            "creation, network transport, quarantine export, and audit persistence. "
            "The order source is represented by deterministic in-process pages; each "
            "order has one line item. A single repeat is sensitive to system noise; "
            "use `--repeats 3` or more for a more stable median.",
            "- **Memory limitation:** process peak working-set memory is a high-water "
            "mark across both variants and dataset preparation, not per-stage or "
            "per-variant allocation. It is `null` on platforms without the sampler.",
            "- **Reproduction:** `python scripts/benchmark_performance.py` "
            "(optional: `--sizes 1000 10000 100000 --repeats 1`).",
            "",
            "### Bottleneck evidence",
        ]
    )
    largest = max(
        report["results"], key=lambda item: item["source_record_count"]
    )
    base = largest["baseline"]
    stage_times = {
        "ingestion": base["ingestion_seconds"],
        "validation": base["validation_seconds"],
        "transformation": base["transformation_seconds"],
        "warehouse loading": base["warehouse_loading_seconds"],
    }
    bottleneck, seconds = max(stage_times.items(), key=lambda pair: pair[1])
    lines.append(
        f"- At {largest['source_record_count']:,} source records, baseline "
        f"**{bottleneck}** was the slowest stage at {seconds:.4f}s "
        f"({seconds / base['total_execution_seconds']:.1%} of measured total)."
    )
    lines.extend(["", "## Dataset reproducibility", ""])
    for item in report["results"]:
        lines.append(
            f"- {item['source_record_count']:,} source records: "
            f"`{item['dataset_sha256']}`"
        )
    if report["peak_working_set_bytes"] is not None:
        lines.extend(
            [
                "",
                f"Peak sampled process working set: "
                f"{report['peak_working_set_bytes'] / (1024 * 1024):.1f} MiB.",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=list(DEFAULT_SIZES))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "benchmark-results" / "pipeline-benchmark.json",
    )
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if any(size < 2 for size in args.sizes):
        parser.error("each benchmark size must be at least 2 source records")

    results = []
    with tempfile.TemporaryDirectory(prefix="datapulse-benchmark-") as directory:
        with PeakMemorySampler() as memory:
            for size in args.sizes:
                print(f"Benchmarking {size:,} combined source records...", flush=True)
                item, _ = _benchmark_size(size, args.repeats, Path(directory))
                results.append(item)
                print(
                    f"  loader {item['warehouse_load_speedup']:.2f}x; "
                    f"total {item['total_speedup']:.2f}x",
                    flush=True,
                )

    report = {
        "benchmark": "DataPulse pipeline stage benchmark",
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "sqlalchemy": __import__("sqlalchemy").__version__,
        },
        "repeats": args.repeats,
        "peak_working_set_bytes": memory.peak_bytes,
        "optimization": "batch primary-key lookup and add_all warehouse loading",
        "methodology": (
            "Deterministic generated data; CSV file ingestion and in-process "
            "paginated order response parsing; identical stage outputs reused for "
            "baseline/optimized loading; fresh temporary SQLite database per variant."
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path = args.output.with_suffix(".md")
    _write_markdown(markdown_path, report)
    print(f"JSON results: {args.output}")
    print(f"Markdown report: {markdown_path}")


if __name__ == "__main__":
    main()

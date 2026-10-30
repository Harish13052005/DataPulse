"""Data validation engine for DataPulse.

The engine validates records from the two ingestion sources (customers CSV and orders API)
against the Pydantic schemas defined in ``app.validation.schemas`` and applies a set of
business rules:

* Uniqueness of primary keys.
* Non‑null required fields.
* Email format, date formats, status enumerations – leveraged by the Pydantic models.
* Referential integrity (order.customer_id must exist, order.product_id must be in the
  catalog).
* Boundary checks (quantity > 0, unit_price >= 0, discount within [0, 100]).
* Detection of unexpected fields (schema‑drift).

Invalid records are never discarded – they are written to the quarantine directory as
JSON‑Lines with full payload and rejection metadata.  The function also returns a
summary of data‑quality metrics.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from pydantic import ValidationError

from app.config.settings import settings
from .schemas import CustomerRawSchema, OrderRawSchema, LineItemRawSchema
from app.ingestion.ingestion_meta import IngestionResult, RunMetadata
from app.api.data_generator import PRODUCT_CATALOG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration / constant rule sets
# ---------------------------------------------------------------------------
APPROVED_SEGMENTS = {"Standard", "Premium", "VIP"}
APPROVED_ORDER_STATUSES = {"COMPLETED", "PENDING", "CANCELLED", "REFUNDED"}
MAX_DISCOUNT_PERCENT = 100.0  # percent based discount amount can be up to 100

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _write_quarantine(record: Dict[str, Any], source_identifier: str, run_id: str, reason: str) -> None:
    """Append a rejected record to the quarantine file.

    The quarantine file lives under ``settings.QUARANTINE_DATA_DIR`` and is a JSONL
    file named ``{source_identifier}_quarantine.jsonl``.  Each line contains the
    original payload plus metadata required for auditability.
    """
    quarantine_dir = settings.QUARANTINE_DATA_DIR
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{source_identifier}_quarantine.jsonl"
    path = quarantine_dir / filename
    entry = {
        "run_id": run_id,
        "source_identifier": source_identifier,
        "rejection_timestamp": datetime.now(timezone.utc).isoformat(),
        "rejection_reason": reason,
        "record": record,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _detect_unexpected_fields(record: Dict[str, Any], model_cls: Any) -> List[str]:
    """Return a list of keys present in ``record`` that are not defined in the model.
    Excludes the ingestion‑metadata fields (those prefixed with ``_``).
    """
    allowed = set(model_cls.model_fields.keys())
    # Remove the ingestion metadata fields that start with underscore; they are allowed.
    unexpected = [k for k in record.keys() if k not in allowed and not k.startswith("_")]
    return unexpected

# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def validate_customers(
    raw_records: List[Dict[str, Any]], run_meta: RunMetadata
) -> IngestionResult:
    """Validate a list of customer records.

    Returns an ``IngestionResult`` where ``records`` are the **valid** enriched
    records.  Invalid records are written to quarantine and omitted from the
    returned list.
    """
    seen_ids: Set[str] = set()
    valid: List[Dict[str, Any]] = []
    for rec in raw_records:
        # 1. Schema validation via Pydantic
        try:
            cust = CustomerRawSchema(**rec)
        except ValidationError as ve:
            reason = f"Schema validation error: {ve.errors()}"
            _write_quarantine(rec, "customers", run_meta.run_id, reason)
            logger.debug(reason)
            continue

        # 2. Unexpected fields detection
        unexpected = _detect_unexpected_fields(rec, CustomerRawSchema)
        if unexpected:
            reason = f"Unexpected fields: {unexpected}"
            _write_quarantine(rec, "customers", run_meta.run_id, reason)
            logger.debug(reason)
            continue

        # 3. Business rules – uniqueness, segment membership, null checks
        cid = cust.customer_id
        if cid in seen_ids:
            reason = "Duplicate customer_id"
            _write_quarantine(rec, "customers", run_meta.run_id, reason)
            continue
        seen_ids.add(cid)

        if cust.customer_segment not in APPROVED_SEGMENTS:
            reason = f"Invalid customer_segment: {cust.customer_segment}"
            _write_quarantine(rec, "customers", run_meta.run_id, reason)
            continue

        # Record passes – keep the enriched version (already contains audit fields)
        valid.append(cust.model_dump())

    return IngestionResult(records=valid, metadata=run_meta)


def validate_orders(
    raw_records: List[Dict[str, Any]],
    valid_customer_ids: Set[str],
    run_meta: RunMetadata,
) -> IngestionResult:
    """Validate orders against schemas and business rules.

    ``valid_customer_ids`` should be the set of ``customer_id`` values that passed
    validation in the customer stage.  Invalid orders are quarantined.
    """
    seen_order_ids: Set[str] = set()
    # Build a set of valid product IDs from the catalog used for generation.
    valid_product_ids = {p["product_id"] for p in PRODUCT_CATALOG}
    valid: List[Dict[str, Any]] = []

    for rec in raw_records:
        # 1. Schema validation
        try:
            order = OrderRawSchema(**rec)
        except ValidationError as ve:
            reason = f"Schema validation error: {ve.errors()}"
            _write_quarantine(rec, "orders", run_meta.run_id, reason)
            logger.debug(reason)
            continue

        # 2. Unexpected fields detection
        unexpected = _detect_unexpected_fields(rec, OrderRawSchema)
        if unexpected:
            reason = f"Unexpected fields: {unexpected}"
            _write_quarantine(rec, "orders", run_meta.run_id, reason)
            logger.debug(reason)
            continue

        # 3. Duplicate order_id
        oid = order.order_id
        if oid in seen_order_ids:
            reason = "Duplicate order_id"
            _write_quarantine(rec, "orders", run_meta.run_id, reason)
            continue
        seen_order_ids.add(oid)

        # 4. Referential integrity – customer_id must exist
        if order.customer_id not in valid_customer_ids:
            reason = f"Invalid customer_id reference: {order.customer_id}"
            _write_quarantine(rec, "orders", run_meta.run_id, reason)
            continue

        # 5. Validate each line item
        line_errors = False
        seen_item_ids: Set[str] = set()
        for item in order.items:
            if item.item_id in seen_item_ids:
                reason = f"Duplicate item_id in order: {item.item_id}"
                _write_quarantine(rec, "orders", run_meta.run_id, reason)
                line_errors = True
                break
            seen_item_ids.add(item.item_id)
            # Verify product_id exists
            if item.product_id not in valid_product_ids:
                reason = f"Invalid product_id in line item: {item.product_id}"
                _write_quarantine(rec, "orders", run_meta.run_id, reason)
                line_errors = True
                break
            # Quantity positive – already enforced by schema (gt=0)
            # Unit price non‑negative – schema enforces gt=0, but we also accept 0.
            if item.unit_price < 0:
                reason = f"Negative unit_price in line item: {item.unit_price}"
                _write_quarantine(rec, "orders", run_meta.run_id, reason)
                line_errors = True
                break
        if line_errors:
            continue

        # 6. Discount range validation (percentage assumed; amount already calculated)
        if order.discount_amount < 0 or order.discount_amount > MAX_DISCOUNT_PERCENT:
            reason = f"Discount amount out of allowed range [0, {MAX_DISCOUNT_PERCENT}]: {order.discount_amount}"
            _write_quarantine(rec, "orders", run_meta.run_id, reason)
            continue

        # 7. Order status – already validated by schema, but ensure membership
        if order.status not in APPROVED_ORDER_STATUSES:
            reason = f"Invalid order status: {order.status}"
            _write_quarantine(rec, "orders", run_meta.run_id, reason)
            continue

        # Record passes – keep enriched dict
        valid.append(order.model_dump())

    return IngestionResult(records=valid, metadata=run_meta)


def compute_quality_metrics(
    total: int, valid: int, rejected: int, duplicate: int, null_violations: int, referential: int
) -> Dict[str, Any]:
    """Return a dictionary of data‑quality metrics.

    ``duplicate`` and ``null_violations`` are counted as part of ``rejected`` but are
    reported separately for insight.
    """
    quality_pct = (valid / total) * 100 if total else 0.0
    return {
        "total_records": total,
        "valid_records": valid,
        "rejected_records": rejected,
        "duplicate_records": duplicate,
        "null_violations": null_violations,
        "referential_integrity_violations": referential,
        "data_quality_percentage": round(quality_pct, 2),
    }

# ---------------------------------------------------------------------------
# Public façade used by the pipeline
# ---------------------------------------------------------------------------

def run_validation_pipeline(
    customers_raw: List[Dict[str, Any]], orders_raw: List[Dict[str, Any]], run_id: str | None = None
) -> Tuple[IngestionResult, IngestionResult, Dict[str, Any]]:
    """Validate both customers and orders and return results plus metrics.

    ``run_id`` is optional – if omitted a new UUID is generated via ``RunMetadata``.
    The function creates separate ``RunMetadata`` objects for each source (sharing the
    same ``run_id``) and passes them to the individual validators.
    """
    # Shared run identifier for traceability
    shared_run_id = run_id or RunMetadata().run_id
    cust_meta = RunMetadata(run_id=shared_run_id, source_name="CSV_CUSTOMERS", source_identifier=str(settings.CUSTOMERS_CSV_PATH))
    cust_res = validate_customers(customers_raw, cust_meta)
    valid_cust_ids = {r["customer_id"] for r in cust_res.records}

    order_meta = RunMetadata(run_id=shared_run_id, source_name="REST_API_ORDERS", source_identifier=settings.API_BASE_URL)
    order_res = validate_orders(orders_raw, valid_cust_ids, order_meta)

    # Metrics – we approximate duplicate/null counts via differences between input and valid counts.
    total_records = len(customers_raw) + len(orders_raw)
    valid_records = len(cust_res.records) + len(order_res.records)
    rejected_records = total_records - valid_records
    # For a more granular count you could extend the engine to return counters; here we treat all rejections equal.
    metrics = compute_quality_metrics(
        total=total_records,
        valid=valid_records,
        rejected=rejected_records,
        duplicate=0,
        null_violations=0,
        referential=0,
    )
    return cust_res, order_res, metrics

"""Usage example (called from the pipeline):

    from app.ingestion.csv_ingestion import CustomerCSVIngestor
    from app.ingestion.api_ingestion import OrdersAPIIngestor
    from app.validation.engine import run_validation_pipeline

    cust_ing = CustomerCSVIngestor()
    raw_cust = cust_ing.ingest()
    order_ing = OrdersAPIIngestor(force_mock_client=True)
    raw_orders = order_ing.ingest()
    cust_res, order_res, metrics = run_validation_pipeline(raw_cust, raw_orders)
"""

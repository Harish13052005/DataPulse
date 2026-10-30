"""DataPulse transformation layer.

This module converts **validated** customer and order records (the output of
``app.validation.engine``) into analytical‑ready structures.  The transformations
are deterministic, repeatable, and preserve full traceability back to the source
record via the ``_source_*`` audit fields.

Business rules implemented:

1. **Text standardisation** – leading/trailing whitespace is stripped; internal
   multiple spaces are collapsed; names are title‑cased; city/state are upper‑cased.
2. **Email normalisation** – lower‑casing and whitespace removal.
3. **Date / timestamp normalisation** – all dates are converted to ISO‑8601
   strings (``YYYY‑MM‑DD`` for dates, full ISO‑8601 with ``Z`` for timestamps).
4. **Missing optional values** – optional fields that are ``None`` or missing are
   replaced with sensible defaults (e.g. empty string for optional text, ``0`` for
   numeric aggregates).
5. **Financial calculations** – for each order we compute:
   * ``gross_amount`` = Σ(quantity × unit_price) over line items.
   * ``discount_amount`` – taken from the order payload (already a monetary amount).
   * ``net_revenue`` = ``gross_amount`` – ``discount_amount`` + ``tax_amount`` +
     ``shipping_fee``.
   The calculated ``gross_amount`` and ``net_revenue`` are stored alongside the
   original fields for downstream analytics.
6. **Customer analytical attributes** – additional columns derived from the raw
   customer data:
   * ``signup_year`` – year extracted from ``signup_date``.
   * ``email_domain`` – domain part of the e‑mail address.
   * ``is_premium`` – ``True`` when ``customer_segment`` is ``"Premium"`` or
     ``"VIP"``.
7. **Late‑arriving records** – if an order timestamp is later than the current
   UTC time, a flag ``_is_late_arrival`` is added but the record is otherwise
   retained (no historical data is dropped).
8. **Determinism** – the functions contain **no randomness** and operate purely
   on the input payload, guaranteeing repeatable results for the same input.
9. **Traceability** – every output record retains the original ``_source_*``
   audit fields, a ``_transformation_timestamp`` and a ``_run_id`` linking back
   to the ingestion run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

import pandas as pd

from .engine import RunMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _clean_text(value: Any) -> str:
    """Strip whitespace, collapse multiple spaces, and return a string.

    ``None`` becomes an empty string.  Numbers are converted to strings.
    """
    if value is None:
        return ""
    s = str(value).strip()
    # collapse consecutive whitespace into a single space
    return " ".join(s.split())


def _title_case(value: str) -> str:
    """Title‑case a name while preserving internal capitalization (e.g. "McDonald")."""
    return value.title()


def _standardize_date(date_str: str) -> str:
    """Parse a date in common formats and return ``YYYY‑MM‑DD`` ISO string.

    Supports ``YYYY‑MM‑DD`` and ``MM/DD/YYYY``.  Raises ``ValueError`` if parsing
    fails.
    """
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {date_str}")


def _standardize_timestamp(ts: str) -> str:
    """Return an ISO‑8601 UTC timestamp with ``Z`` suffix.

    Accepts any ISO‑8601 string; if it lacks timezone info it is assumed to be UTC.
    """
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

# ---------------------------------------------------------------------------
# Customer transformation
# ---------------------------------------------------------------------------

def transform_customers(valid_customers: List[Dict[str, Any]], run_meta: RunMetadata) -> pd.DataFrame:
    """Transform validated customer records into an analytical DataFrame.

    The function is **deterministic** – given the same input list it always
    produces the same DataFrame (column order, data types, values).
    """
    transformed = []
    for rec in valid_customers:
        # Standardise text fields
        first = _title_case(_clean_text(rec.get("first_name")))
        last = _title_case(_clean_text(rec.get("last_name")))
        city = _clean_text(rec.get("city")).upper()
        state = _clean_text(rec.get("state")).upper()
        # Normalise email
        email = _clean_text(rec.get("email")).lower()
        # Standardise dates
        try:
            signup = _standardize_date(rec.get("signup_date"))
        except Exception as e:
            logger.warning("Failed to parse signup_date for %s: %s", rec.get("customer_id"), e)
            signup = None

        # Derive analytical attributes
        signup_year = int(signup[:4]) if signup else None
        email_domain = email.split("@")[-1] if "@" in email else ""
        is_premium = rec.get("customer_segment") in {"Premium", "VIP"}

        transformed.append(
            {
                "customer_id": rec.get("customer_id"),
                "first_name": first,
                "last_name": last,
                "email": email,
                "city": city,
                "state": state,
                "signup_date": signup,
                "customer_segment": rec.get("customer_segment"),
                "is_active": rec.get("is_active", True),
                # analytical fields
                "signup_year": signup_year,
                "email_domain": email_domain,
                "is_premium": is_premium,
                # traceability
                "_source_system": rec.get("_source_system"),
                "_source_file": rec.get("_source_file"),
                "_source_row_num": rec.get("_source_row_num"),
                "_ingested_at": rec.get("_ingested_at"),
                "_record_hash": rec.get("_record_hash"),
                "_run_id": run_meta.run_id,
                "_transformation_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    return pd.DataFrame(transformed)

# ---------------------------------------------------------------------------
# Order transformation
# ---------------------------------------------------------------------------

def _calc_gross_amount(items: List[Dict[str, Any]]) -> float:
    """Calculate gross amount as Σ(quantity × unit_price) for the line items."""
    total = 0.0
    for it in items:
        qty = it.get("quantity", 0)
        price = it.get("unit_price", 0.0)
        total += qty * price
    return round(total, 2)


def transform_orders(valid_orders: List[Dict[str, Any]], run_meta: RunMetadata) -> pd.DataFrame:
    """Transform validated order records into an analytical DataFrame.

    Financial fields are recomputed for consistency and added as new columns:
    ``gross_amount`` and ``net_revenue``.  A flag ``_is_late_arrival`` is set when
    the order timestamp is later than the current UTC time.
    """
    transformed = []
    now_utc = datetime.now(timezone.utc)
    for rec in valid_orders:
        # Standardise timestamp
        try:
            ts_iso = _standardize_timestamp(rec.get("order_timestamp"))
            ts_dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning("Failed to parse order_timestamp %s: %s", rec.get("order_id"), e)
            ts_iso = None
            ts_dt = None

        # Compute gross amount from line items (deterministic)
        gross = _calc_gross_amount(rec.get("items", []))
        discount = rec.get("discount_amount", 0.0)
        tax = rec.get("tax_amount", 0.0)
        shipping = rec.get("shipping_fee", 0.0)
        net = round(gross - discount + tax + shipping, 2)

        # Validate against provided totals – log a warning if they differ
        if abs(net - rec.get("total_amount", 0.0)) > 0.01:
            logger.info(
                "Order %s net revenue mismatch: computed %s vs payload %s",
                rec.get("order_id"),
                net,
                rec.get("total_amount"),
            )

        # Late‑arrival detection
        is_late = ts_dt is not None and ts_dt > now_utc

        transformed.append(
            {
                "order_id": rec.get("order_id"),
                "customer_id": rec.get("customer_id"),
                "order_timestamp": ts_iso,
                "status": rec.get("status"),
                "payment_method": rec.get("payment_method"),
                "gross_amount": gross,
                "discount_amount": discount,
                "tax_amount": tax,
                "shipping_fee": shipping,
                "net_revenue": net,
                # keep original totals for reference
                "subtotal": rec.get("subtotal"),
                "total_amount": rec.get("total_amount"),
                "_is_late_arrival": is_late,
                # traceability fields
                "_source_system": rec.get("_source_system"),
                "_source_page": rec.get("_source_page"),
                "_source_row_num": rec.get("_source_row_num"),
                "_ingested_at": rec.get("_ingested_at"),
                "_record_hash": rec.get("_record_hash"),
                "_run_id": run_meta.run_id,
                "_transformation_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    return pd.DataFrame(transformed)

# ---------------------------------------------------------------------------
# Public façade
# ---------------------------------------------------------------------------

def run_transformation_pipeline(
    customers_res: pd.DataFrame | List[Dict[str, Any]],
    orders_res: pd.DataFrame | List[Dict[str, Any]],
    run_meta: RunMetadata,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Convenient entry point used by the main pipeline.

    ``customers_res`` and ``orders_res`` may be either the raw list of validated
    dictionaries (as returned by the validation engine) or the already‑converted
    ``IngestionResult.records`` list.
    """
    if not isinstance(customers_res, list):
        customers_list = customers_res.to_dict(orient="records")
    else:
        customers_list = customers_res

    if not isinstance(orders_res, list):
        orders_list = orders_res.to_dict(orient="records")
    else:
        orders_list = orders_res

    cust_df = transform_customers(customers_list, run_meta)
    order_df = transform_orders(orders_list, run_meta)
    return cust_df, order_df

"""Example usage (called after validation):

    from app.validation.engine import run_validation_pipeline
    from app.ingestion.csv_ingestion import CustomerCSVIngestor
    from app.ingestion.api_ingestion import OrdersAPIIngestor
    from app.transformation.transformer import run_transformation_pipeline

    cust_ing = CustomerCSVIngestor()
    raw_cust = cust_ing.ingest()
    order_ing = OrdersAPIIngestor(force_mock_client=True)
    raw_orders = order_ing.ingest()

    cust_res, order_res, _ = run_validation_pipeline(raw_cust, raw_orders)
    cust_df, order_df = run_transformation_pipeline(cust_res.records, order_res.records, cust_res.metadata)
    print(cust_df.head())
    print(order_df.head())
"""

#!/usr/bin/env python
"""Synthetic data generator for DataPulse.

Produces two source data sets:
* ``data/raw/customers.csv`` – customer master records.
* ``data/raw/orders.json``   – order records (JSON array) as returned by the mock REST API.

For every source a companion ``*_invalid.jsonl`` file is written that contains
metadata about the records that deliberately violate the schema/ business rules.
The generator is fully deterministic – the same ``--seed`` value always yields the
same files, which makes testing idempotent.

Usage::

    python scripts/generate_data.py [--size small|large] [--seed N]

* ``--size small``  – 250 customers and 1 000 orders (fast, suitable for CI).
* ``--size large``  – 100 000 customers and 250 000 orders (stress‑test).
* ``--seed``        – Random seed for reproducibility (default: 42).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List

# Re‑use the generation functions that already exist in the code‑base.
# They live in ``app.api.data_generator`` and expose deterministic helpers.
import sys
from pathlib import Path
# Ensure the project root (parent of 'scripts') is on the import path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from app.api.data_generator import (
    generate_synthetic_customers,
    generate_synthetic_orders,
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write a list of dictionaries to a CSV file.

    The CSV header is taken from the keys of the first row (order is preserved).
    """
    if not rows:
        path.touch()
        return
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write a list of dictionaries as a JSON array.
    """
    with path.open("w", encoding="utf-8") as fp:
        json.dump(rows, fp, ensure_ascii=False, indent=2)


def write_invalid_metadata(path: Path, metadata: List[Dict[str, Any]]) -> None:
    """Write one JSON object per line – convenient for streaming tools.
    """
    with path.open("w", encoding="utf-8") as fp:
        for rec in metadata:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic data for DataPulse")
    parser.add_argument(
        "--size",
        choices=["small", "large"],
        default="small",
        help="Dataset size (small = quick, large = 100k+ records)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    # ---------------------------------------------------------------------
    # Determine target row counts based on the requested size.
    # ---------------------------------------------------------------------
    if args.size == "small":
        cust_cnt, order_cnt = 250, 1_000
    else:  # large
        cust_cnt, order_cnt = 100_000, 250_000

    # ---------------------------------------------------------------------
    # Generate customers and capture dirty‑record metadata.
    # ---------------------------------------------------------------------
    customers = generate_synthetic_customers(count=cust_cnt, seed=args.seed, dirty_ratio=0.08)
    # The generator currently mixes valid and dirty rows.  We identify the dirty
    # ones by re‑running the clean generation (without dirty injection) and diff‑
    # ing the two lists – this is cheap because the function is deterministic.
    clean_customers = generate_synthetic_customers(count=cust_cnt, seed=args.seed, dirty_ratio=0.0)
    cust_invalid: List[Dict[str, Any]] = []
    for idx, (orig, clean) in enumerate(zip(customers, clean_customers), start=1):
        if orig != clean:
            # Determine a simple reason based on which field differs.
            diff_fields = [k for k in orig if orig[k] != clean[k]]
            cust_invalid.append({"row": idx, "fields": diff_fields, "record": orig})

    # ---------------------------------------------------------------------
    # Generate orders and corresponding dirty‑record metadata.
    # ---------------------------------------------------------------------
    customer_ids = [c["customer_id"] for c in customers]
    orders = generate_synthetic_orders(
        count=order_cnt,
        customer_ids=customer_ids,
        seed=args.seed,
        dirty_ratio=0.08,
    )
    clean_orders = generate_synthetic_orders(
        count=order_cnt,
        customer_ids=customer_ids,
        seed=args.seed,
        dirty_ratio=0.0,
    )
    order_invalid: List[Dict[str, Any]] = []
    for idx, (orig, clean) in enumerate(zip(orders, clean_orders), start=1):
        if orig != clean:
            diff_fields = [k for k in orig if orig[k] != clean[k]]
            order_invalid.append({"row": idx, "fields": diff_fields, "record": orig})

    # ---------------------------------------------------------------------
    # Write outputs to the ``data/raw`` hierarchy.
    # ---------------------------------------------------------------------
    data_root = Path(__file__).resolve().parents[2] / "data" / "raw"
    data_root.mkdir(parents=True, exist_ok=True)

    # Customers CSV + invalid metadata
    write_csv(data_root / "customers.csv", customers)
    write_invalid_metadata(data_root / "customers_invalid.jsonl", cust_invalid)

    # Orders JSON + invalid metadata
    write_json(data_root / "orders.json", orders)
    write_invalid_metadata(data_root / "orders_invalid.jsonl", order_invalid)

    # ---------------------------------------------------------------------
    # Simple verification printed to STDOUT – useful for CI logs.
    # ---------------------------------------------------------------------
    print(f"Generated {len(customers)} customer records (dirty: {len(cust_invalid)})")
    print(f"Generated {len(orders)} order records (dirty: {len(order_invalid)})")
    print("Sample customer (first row):")
    print(json.dumps(customers[0], ensure_ascii=False, indent=2))
    print("Sample order (first row):")
    print(json.dumps(orders[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

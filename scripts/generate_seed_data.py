"""
Seed Data Generation Script for DataPulse Platform.

Generates deterministic synthetic customer CSV data with fixed random seed,
and creates sample mock datasets in data/raw and data/sample.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.api.data_generator import (
    PRODUCT_CATALOG,
    export_customers_to_csv,
    generate_synthetic_customers,
)


def run_seed_generation() -> None:
    """Generate deterministic seed data for customers and products."""
    settings.ensure_directories()

    print(f"Generating deterministic synthetic customers with seed={settings.RANDOM_SEED}...")
    customers = generate_synthetic_customers(
        count=250,
        seed=settings.RANDOM_SEED,
        dirty_ratio=settings.INJECT_DIRTY_DATA_RATIO
    )

    csv_path = settings.CUSTOMERS_CSV_PATH
    export_customers_to_csv(csv_path, customers)
    print(f"Exported {len(customers)} customer records to {csv_path}")

    # Also save copy in data/sample
    sample_csv_path = settings.SAMPLE_DATA_DIR / "customers_sample.csv"
    export_customers_to_csv(sample_csv_path, customers)
    print(f"Saved sample copy to {sample_csv_path}")
    print("Seed data generation completed successfully!")


if __name__ == "__main__":
    run_seed_generation()

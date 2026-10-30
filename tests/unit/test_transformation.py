"""
Unit Tests for Data Transformations and Dimensional Entities.
"""

from __future__ import annotations

from datetime import date
from app.transformation.cleaner import DataCleaner
from app.transformation.dimensional_transformer import DimensionalTransformer


def test_data_cleaner_functions():
    assert DataCleaner.clean_text("  hello   world  ") == "hello world"
    assert DataCleaner.clean_name("john doe") == "John Doe"
    assert DataCleaner.clean_email(" USER@DOMAIN.COM ") == "user@domain.com"
    assert DataCleaner.clean_state(" california ") == "CA"

    dt = DataCleaner.normalize_timestamp("2023-05-10T12:00:00Z")
    assert dt.year == 2023
    assert dt.month == 5
    assert dt.tzinfo is not None


def test_surrogate_key_generation_deterministic():
    key1 = DimensionalTransformer.generate_surrogate_key("CUST", "CUST-1001")
    key2 = DimensionalTransformer.generate_surrogate_key("CUST", "CUST-1001")
    key3 = DimensionalTransformer.generate_surrogate_key("CUST", "CUST-1002")

    assert isinstance(key1, int)
    assert key1 == key2
    assert key1 != key3


def test_surrogate_keys_support_large_dimensions_without_32_bit_collisions():
    keys = {
        DimensionalTransformer.generate_surrogate_key("CUST", f"BENCH-C-{index:07d}")
        for index in range(1, 50_001)
    }

    assert len(keys) == 50_000, (
        "The benchmark-scale customer key set must not collide in the warehouse PK."
    )
    assert max(keys) > 2**31 - 1, "Surrogate keys should use the expanded 64-bit range."


def test_build_date_dimension_record():
    test_dt = date(2023, 10, 31)
    dim_d = DimensionalTransformer.build_date_dimension_record(test_dt)

    assert dim_d["date_key"] == 20231031
    assert dim_d["year"] == 2023
    assert dim_d["month_num"] == 10
    assert dim_d["month_name"] == "October"
    assert dim_d["day_name"] == "Tuesday"
    assert dim_d["is_weekend"] is False
    assert dim_d["is_month_end"] is True


def test_transform_products(sample_products):
    dim_prods = DimensionalTransformer.transform_products(sample_products)
    assert len(dim_prods) == len(sample_products)
    for p in dim_prods:
        assert "product_key" in p
        assert p["price_tier"] in ("Budget", "Standard", "Premium", "Luxury")


def test_transform_orders_and_items(sample_valid_order):
    cust_key_lookup = {"CUST-9001": 12345}
    prod_key_lookup = {"PROD-001": 54321, "PROD-006": 98765}

    fact_orders, fact_items, dim_dates = DimensionalTransformer.transform_orders_and_items(
        valid_orders=[sample_valid_order],
        customer_key_lookup=cust_key_lookup,
        product_key_lookup=prod_key_lookup
    )

    assert len(fact_orders) == 1
    assert len(fact_items) == 2
    assert len(dim_dates) == 1

    fo = fact_orders[0]
    assert fo["order_id"] == "ORD-9001"
    assert fo["customer_key"] == 12345
    assert fo["status"] == "COMPLETED"
    assert fo["item_count"] == 2

"""
Unit Tests for Analytical Queries and Business Intelligence Engine.
"""

from __future__ import annotations

import pandas as pd
from app.analytics.queries import AnalyticsQueries
from app.warehouse.connection import engine


def test_analytical_executive_kpis():
    queries = AnalyticsQueries(engine)
    kpis = queries.get_executive_kpis()

    assert isinstance(kpis, dict)
    assert "total_customers" in kpis
    assert "total_orders" in kpis
    assert "total_net_revenue" in kpis


def test_analytical_rfm_segmentation():
    queries = AnalyticsQueries(engine)
    rfm_df = queries.get_rfm_segmentation()

    assert isinstance(rfm_df, pd.DataFrame)
    expected_cols = {"customer_id", "monetary", "frequency", "recency_days", "rfm_segment"}
    assert expected_cols.issubset(set(rfm_df.columns))


def test_analytical_monthly_trends():
    queries = AnalyticsQueries(engine)
    trends_df = queries.get_monthly_revenue_trends()

    assert isinstance(trends_df, pd.DataFrame)
    assert "year_month" in trends_df.columns
    assert "net_revenue" in trends_df.columns
    assert "total_orders" in trends_df.columns


def test_analytical_top_products():
    queries = AnalyticsQueries(engine)
    prods_df = queries.get_top_products_performance(limit=5)

    assert isinstance(prods_df, pd.DataFrame)
    assert len(prods_df) <= 5
    if not prods_df.empty:
        assert "product_name" in prods_df.columns
        assert "net_sales" in prods_df.columns
        sales = prods_df["net_sales"].tolist()
        assert sales == sorted(sales, reverse=True)


def test_analytical_category_breakdown():
    queries = AnalyticsQueries(engine)
    cat_df = queries.get_category_breakdown()

    assert isinstance(cat_df, pd.DataFrame)
    assert "category" in cat_df.columns
    assert "net_revenue" in cat_df.columns

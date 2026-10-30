"""Analytical query correctness against a deterministic warehouse fixture."""

from __future__ import annotations

from app.analytics.queries import AnalyticsQueries


def test_analytical_queries_return_seeded_warehouse_values(test_engine, seeded_warehouse):
    queries = AnalyticsQueries(test_engine)

    kpis = queries.get_executive_kpis()
    trends = queries.get_monthly_revenue_trends()
    products = queries.get_top_products_performance(limit=5)
    categories = queries.get_category_breakdown()
    segments = queries.get_customer_clv_by_segment()
    rfm = queries.get_rfm_segmentation()

    assert kpis["total_customers"] == 1, "KPI query should read the isolated customer row."
    assert kpis["total_orders"] == 1, "KPI query should read the isolated order row."
    assert kpis["total_net_revenue"] == 90.0
    assert trends.iloc[0]["year_month"] == "2024-01"
    assert trends.iloc[0]["total_orders"] == 1
    assert trends.iloc[0]["net_revenue"] == 90.0
    assert products.iloc[0]["product_id"] == "PROD-001"
    assert products.iloc[0]["total_units_sold"] == 2
    assert products.iloc[0]["net_sales"] == 90.0
    assert categories.iloc[0]["category"] == "Electronics"
    assert categories.iloc[0]["net_revenue"] == 90.0
    assert segments.iloc[0]["total_customers"] == 1
    assert segments.iloc[0]["clv_per_customer"] == 90.0
    assert rfm.iloc[0]["customer_id"] == seeded_warehouse["customer"]["customer_id"]
    assert rfm.iloc[0]["frequency"] == 1


def test_analytical_queries_return_empty_shapes_without_data(test_engine):
    queries = AnalyticsQueries(test_engine)

    assert queries.get_monthly_revenue_trends().empty
    assert queries.get_top_products_performance(limit=5).empty
    assert queries.get_rfm_segmentation().empty
    assert queries.get_customer_clv_by_segment().empty
    assert queries.get_category_breakdown().empty

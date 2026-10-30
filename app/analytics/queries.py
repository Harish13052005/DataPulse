"""
Analytical SQL Queries & Metrics Engine for DataPulse Platform.

Provides optimized analytical queries:
1. RFM Customer Segmentation
2. Monthly Revenue Trends, MoM Growth & AOV
3. Top Performing Products & Categories
4. Customer Lifetime Value (CLV) by Segment & Geography
5. Executive Scorecard KPIs
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd
from sqlalchemy import text
from app.warehouse.connection import engine


class AnalyticsQueries:
    """Executes high-performance analytical queries against the warehouse."""

    def __init__(self, db_engine=None):
        self.engine = db_engine or engine

    def get_rfm_segmentation(self) -> pd.DataFrame:
        """Compute RFM scores and segments for customers."""
        query = text("""
            WITH customer_aggregates AS (
                SELECT 
                    c.customer_id,
                    c.full_name,
                    c.email,
                    c.customer_segment,
                    c.state,
                    c.signup_date,
                    MAX(o.order_timestamp) AS last_order_date,
                    COUNT(o.order_key) AS frequency,
                    COALESCE(SUM(o.net_amount), 0.0) AS monetary,
                    COALESCE(AVG(o.net_amount), 0.0) AS avg_order_value
                FROM dim_customers c
                LEFT JOIN fact_orders o 
                    ON c.customer_key = o.customer_key 
                    AND o.status = 'COMPLETED'
                GROUP BY 
                    c.customer_id, c.full_name, c.email, c.customer_segment, c.state, c.signup_date
            ),
            ref_date AS (
                SELECT COALESCE(MAX(order_timestamp), CURRENT_TIMESTAMP) AS max_dt 
                FROM fact_orders
            ),
            rfm_metrics AS (
                SELECT 
                    ca.*,
                    ROUND(
                        (JULIANDAY(rd.max_dt) - JULIANDAY(COALESCE(ca.last_order_date, ca.signup_date)))
                    ) AS recency_days
                FROM customer_aggregates ca
                CROSS JOIN ref_date rd
            )
            SELECT 
                customer_id,
                full_name,
                email,
                customer_segment,
                state,
                signup_date,
                last_order_date,
                recency_days,
                frequency,
                ROUND(monetary, 2) AS monetary,
                ROUND(avg_order_value, 2) AS avg_order_value,
                CASE 
                    WHEN frequency >= 4 AND monetary >= 1500 THEN 'Champions'
                    WHEN frequency >= 3 AND monetary >= 800 THEN 'Loyal Customers'
                    WHEN frequency >= 2 AND recency_days <= 90 THEN 'Potential Loyalists'
                    WHEN frequency = 1 AND recency_days <= 60 THEN 'New Customers'
                    WHEN frequency >= 2 AND recency_days > 120 THEN 'At Risk'
                    WHEN frequency = 0 THEN 'Never Purchased'
                    ELSE 'Needs Attention'
                END AS rfm_segment
            FROM rfm_metrics
            ORDER BY monetary DESC, frequency DESC;
        """)
        with self.engine.connect() as conn:
            return pd.read_sql(query, conn)

    def get_monthly_revenue_trends(self) -> pd.DataFrame:
        """Calculate monthly revenue, orders, and Month-over-Month (MoM) growth."""
        query = text("""
            WITH monthly_summary AS (
                SELECT 
                    d.year,
                    d.month_num,
                    d.year || '-' || CASE WHEN d.month_num < 10 THEN '0' || d.month_num ELSE '' || d.month_num END AS year_month,
                    COUNT(o.order_key) AS total_orders,
                    SUM(CASE WHEN o.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_orders,
                    SUM(CASE WHEN o.status = 'REFUNDED' THEN 1 ELSE 0 END) AS refunded_orders,
                    ROUND(SUM(o.subtotal), 2) AS gross_revenue,
                    ROUND(SUM(o.discount_amount), 2) AS total_discounts,
                    ROUND(SUM(o.tax_amount), 2) AS total_taxes,
                    ROUND(SUM(o.shipping_fee), 2) AS total_shipping,
                    ROUND(SUM(o.net_amount), 2) AS net_revenue,
                    ROUND(AVG(o.net_amount), 2) AS average_order_value
                FROM fact_orders o
                JOIN dim_date d ON o.order_date_key = d.date_key
                GROUP BY d.year, d.month_num
                ORDER BY d.year ASC, d.month_num ASC
            )
            SELECT 
                year,
                month_num,
                year_month,
                total_orders,
                completed_orders,
                refunded_orders,
                gross_revenue,
                total_discounts,
                net_revenue,
                average_order_value,
                ROUND(
                    ((net_revenue - LAG(net_revenue, 1) OVER (ORDER BY year, month_num)) / 
                    NULLIF(LAG(net_revenue, 1) OVER (ORDER BY year, month_num), 0.0)) * 100.0, 
                    2
                ) AS mom_growth_pct
            FROM monthly_summary
            ORDER BY year_month ASC;
        """)
        with self.engine.connect() as conn:
            return pd.read_sql(query, conn)

    def get_top_products_performance(self, limit: int = 10) -> pd.DataFrame:
        """Retrieve top performing products by total net revenue."""
        query = text(f"""
            SELECT 
                p.product_id,
                p.product_name,
                p.category,
                p.price_tier,
                p.unit_price,
                COUNT(DISTINCT oi.order_key) AS total_orders,
                SUM(oi.quantity) AS total_units_sold,
                ROUND(SUM(oi.line_total), 2) AS gross_sales,
                ROUND(SUM(oi.discount_allocated), 2) AS total_discounts,
                ROUND(SUM(oi.line_total - oi.discount_allocated), 2) AS net_sales
            FROM fact_order_items oi
            JOIN dim_products p ON oi.product_key = p.product_key
            JOIN fact_orders o ON oi.order_key = o.order_key
            WHERE o.status = 'COMPLETED'
            GROUP BY p.product_id, p.product_name, p.category, p.price_tier, p.unit_price
            ORDER BY net_sales DESC
            LIMIT {limit};
        """)
        with self.engine.connect() as conn:
            return pd.read_sql(query, conn)

    def get_category_breakdown(self) -> pd.DataFrame:
        """Summarize revenue and order volume by category."""
        query = text("""
            SELECT 
                p.category,
                COUNT(DISTINCT p.product_id) AS product_count,
                COUNT(DISTINCT oi.order_key) AS order_count,
                SUM(oi.quantity) AS total_units,
                ROUND(SUM(oi.line_total - oi.discount_allocated), 2) AS net_revenue,
                ROUND(AVG(p.unit_price), 2) AS avg_product_price
            FROM fact_order_items oi
            JOIN dim_products p ON oi.product_key = p.product_key
            JOIN fact_orders o ON oi.order_key = o.order_key
            WHERE o.status = 'COMPLETED'
            GROUP BY p.category
            ORDER BY net_revenue DESC;
        """)
        with self.engine.connect() as conn:
            return pd.read_sql(query, conn)

    def get_customer_clv_by_segment(self) -> pd.DataFrame:
        """Calculate CLV by customer demographic tier."""
        query = text("""
            SELECT 
                c.customer_segment,
                COUNT(DISTINCT c.customer_key) AS total_customers,
                COUNT(DISTINCT o.order_key) AS total_orders,
                ROUND(COALESCE(SUM(o.net_amount), 0.0), 2) AS total_revenue,
                ROUND(COALESCE(AVG(o.net_amount), 0.0), 2) AS avg_order_value,
                ROUND(COALESCE(SUM(o.net_amount), 0.0) / NULLIF(COUNT(DISTINCT c.customer_key), 0), 2) AS clv_per_customer
            FROM dim_customers c
            LEFT JOIN fact_orders o 
                ON c.customer_key = o.customer_key 
                AND o.status = 'COMPLETED'
            GROUP BY c.customer_segment
            ORDER BY total_revenue DESC;
        """)
        with self.engine.connect() as conn:
            return pd.read_sql(query, conn)

    def get_executive_kpis(self) -> Dict[str, Any]:
        """Compute top-level executive KPI scorecard."""
        query = text("""
            SELECT 
                (SELECT COUNT(*) FROM dim_customers) AS total_customers,
                (SELECT COUNT(*) FROM dim_customers WHERE is_active = 1) AS active_customers,
                (SELECT COUNT(*) FROM fact_orders) AS total_orders,
                (SELECT COUNT(*) FROM fact_orders WHERE status = 'COMPLETED') AS completed_orders,
                (SELECT ROUND(COALESCE(SUM(net_amount), 0.0), 2) FROM fact_orders WHERE status = 'COMPLETED') AS total_net_revenue,
                (SELECT ROUND(COALESCE(AVG(net_amount), 0.0), 2) FROM fact_orders WHERE status = 'COMPLETED') AS average_order_value,
                (SELECT COUNT(*) FROM quarantine_records) AS total_quarantined_records,
                (SELECT COUNT(*) FROM pipeline_runs) AS total_pipeline_runs
        """)
        with self.engine.connect() as conn:
            row = conn.execute(query).mappings().fetchone()
            return dict(row) if row else {}

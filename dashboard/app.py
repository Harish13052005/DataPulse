"""
DataPulse Intelligent Data Engineering & Analytics Platform - Streamlit Dashboard.

Provides executive intelligence, dimensional warehouse exploration,
RFM customer segmentation, and real-time pipeline audit & quarantine monitoring.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import altair as alt
import pandas as pd
import streamlit as st

# Setup python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.analytics.queries import AnalyticsQueries
from app.pipeline import DataPulsePipeline
from app.warehouse.connection import engine, get_db_session
from app.warehouse.models import (
    DimCustomer,
    DimDate,
    DimProduct,
    FactOrder,
    FactOrderItem,
    PipelineRun,
    QuarantineRecord,
)

# Page configuration
st.set_page_config(
    page_title="DataPulse Analytics Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

queries = AnalyticsQueries(engine)


# -----------------------------------------------------------------------------
# Sidebar Navigation & Controls
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ DataPulse")
    st.caption("Intelligent Data Engineering & Analytics Platform")
    st.markdown("---")

    st.subheader("Platform Info")
    st.info(
        f"**Environment:** `{settings.APP_ENV}`\n\n"
        f"**Database:** `{settings.DATABASE_URL.split('///')[-1]}`\n\n"
        f"**Deterministic Seed:** `{settings.RANDOM_SEED}`"
    )

    st.markdown("---")
    st.subheader("Pipeline Actions")
    if st.button("🚀 Trigger Pipeline Execution", use_container_width=True, type="primary"):
        with st.spinner("Executing DataPulse ELT Pipeline..."):
            pipeline = DataPulsePipeline()
            result = pipeline.run()
            st.success(f"Pipeline {result.run_id} completed successfully in {result.duration_seconds:.2f}s!")
            st.rerun()

    st.markdown("---")
    st.caption("Associate AI Forward Deployed Engineer Assessment")


# -----------------------------------------------------------------------------
# Main Header & Executive Scorecard
# -----------------------------------------------------------------------------
st.title("📊 E-Commerce Data Engineering & Business Intelligence")
st.markdown(
    "Live dimensional star schema warehouse ingesting **Source 1 (Customer CSV)** and **Source 2 (Orders REST API)** "
    "with strict schema validation, business rule enforcement, and non-destructive quarantine auditing."
)

kpis = queries.get_executive_kpis()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric(
        label="Net Revenue",
        value=f"${kpis.get('total_net_revenue', 0.0):,.2f}",
        delta="Completed Orders"
    )
with col2:
    st.metric(
        label="Total Orders",
        value=f"{kpis.get('total_orders', 0):,}",
        delta=f"{kpis.get('completed_orders', 0):,} Completed"
    )
with col3:
    st.metric(
        label="Average Order Value",
        value=f"${kpis.get('average_order_value', 0.0):,.2f}"
    )
with col4:
    st.metric(
        label="Active Customers",
        value=f"{kpis.get('active_customers', 0):,}",
        delta=f"Of {kpis.get('total_customers', 0):,} Total"
    )
with col5:
    total_quar = kpis.get("total_quarantined_records", 0)
    st.metric(
        label="Quarantined Records",
        value=f"{total_quar:,}",
        delta="Non-destructive",
        delta_color="inverse" if total_quar > 0 else "normal"
    )

st.markdown("---")


# -----------------------------------------------------------------------------
# Tabbed Workspace
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Executive & Revenue Trends",
    "👥 RFM Customer Intelligence",
    "📦 Product & Category Insights",
    "🛡️ Quality & Quarantine Monitor",
    "🗄️ Dimensional Warehouse Explorer"
])


# -----------------------------------------------------------------------------
# TAB 1: Executive & Revenue Trends
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Monthly Revenue Trends & Order Dynamics")
    trends_df = queries.get_monthly_revenue_trends()

    if not trends_df.empty:
        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            st.markdown("#### Monthly Gross vs. Net Revenue ($)")
            rev_chart = alt.Chart(trends_df).mark_line(point=True).encode(
                x=alt.X("year_month:N", title="Month (YYYY-MM)"),
                y=alt.Y("net_revenue:Q", title="Net Revenue ($)"),
                tooltip=["year_month", "net_revenue", "gross_revenue", "total_discounts", "mom_growth_pct"]
            ).properties(height=350)
            st.altair_chart(rev_chart, use_container_width=True)

        with col_chart2:
            st.markdown("#### Order Volume & Completion Breakdown")
            order_chart = alt.Chart(trends_df).mark_bar().encode(
                x=alt.X("year_month:N", title="Month (YYYY-MM)"),
                y=alt.Y("completed_orders:Q", title="Completed Orders"),
                color=alt.value("#2b8a3e"),
                tooltip=["year_month", "total_orders", "completed_orders", "refunded_orders"]
            ).properties(height=350)
            st.altair_chart(order_chart, use_container_width=True)

        st.markdown("#### Detailed Monthly Trend Matrix")
        st.dataframe(
            trends_df[[
                "year_month", "total_orders", "completed_orders", "refunded_orders",
                "gross_revenue", "total_discounts", "net_revenue", "average_order_value", "mom_growth_pct"
            ]],
            use_container_width=True
        )
    else:
        st.warning("No order trend data available in the warehouse yet. Run the pipeline to populate.")


# -----------------------------------------------------------------------------
# TAB 2: RFM Customer Intelligence
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("RFM (Recency, Frequency, Monetary) Customer Segmentation")
    rfm_df = queries.get_rfm_segmentation()

    if not rfm_df.empty:
        col_rfm1, col_rfm2 = st.columns([1, 2])

        with col_rfm1:
            st.markdown("#### Segment Distribution")
            seg_counts = rfm_df["rfm_segment"].value_counts().reset_index()
            seg_counts.columns = ["Segment", "Count"]

            pie_chart = alt.Chart(seg_counts).mark_arc(innerRadius=50).encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color(field="Segment", type="nominal"),
                tooltip=["Segment", "Count"]
            ).properties(height=320)
            st.altair_chart(pie_chart, use_container_width=True)

        with col_rfm2:
            st.markdown("#### Customer Lifetime Value (CLV) by Segment")
            clv_df = queries.get_customer_clv_by_segment()
            clv_chart = alt.Chart(clv_df).mark_bar().encode(
                x=alt.X("customer_segment:N", title="Segment"),
                y=alt.Y("total_revenue:Q", title="Total Net Revenue ($)"),
                color=alt.Color("customer_segment:N", legend=None),
                tooltip=["customer_segment", "total_customers", "total_orders", "total_revenue", "clv_per_customer"]
            ).properties(height=320)
            st.altair_chart(clv_chart, use_container_width=True)

        st.markdown("#### Customer RFM Scoreboard")
        selected_seg = st.selectbox(
            "Filter by RFM Segment:",
            options=["ALL"] + list(rfm_df["rfm_segment"].unique())
        )
        filtered_rfm = rfm_df if selected_seg == "ALL" else rfm_df[rfm_df["rfm_segment"] == selected_seg]

        st.dataframe(
            filtered_rfm[[
                "customer_id", "full_name", "email", "state", "rfm_segment",
                "recency_days", "frequency", "monetary", "avg_order_value"
            ]],
            use_container_width=True,
            height=300
        )
    else:
        st.warning("No customer RFM metrics available.")


# -----------------------------------------------------------------------------
# TAB 3: Product & Category Insights
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("Product Performance & Category Distribution")

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.markdown("#### Top 10 Products by Net Revenue")
        top_prods = queries.get_top_products_performance(limit=10)
        if not top_prods.empty:
            prod_bar = alt.Chart(top_prods).mark_bar().encode(
                y=alt.Y("product_name:N", sort="-x", title="Product"),
                x=alt.X("net_sales:Q", title="Net Sales ($)"),
                color=alt.Color("category:N"),
                tooltip=["product_name", "category", "unit_price", "total_units_sold", "net_sales"]
            ).properties(height=350)
            st.altair_chart(prod_bar, use_container_width=True)

    with col_p2:
        st.markdown("#### Sales by Product Category")
        cat_df = queries.get_category_breakdown()
        if not cat_df.empty:
            cat_bar = alt.Chart(cat_df).mark_bar().encode(
                x=alt.X("category:N", title="Category"),
                y=alt.Y("net_revenue:Q", title="Net Revenue ($)"),
                color=alt.value("#1c7ed6"),
                tooltip=["category", "product_count", "order_count", "total_units", "net_revenue"]
            ).properties(height=350)
            st.altair_chart(cat_bar, use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 4: Quality & Quarantine Monitor
# -----------------------------------------------------------------------------
with tab4:
    st.subheader("🛡️ Data Quality & Quarantine Monitor")
    st.markdown(
        "DataPulse adheres to the engineering principle: **Never silently discard invalid records**. "
        "Every record violating schema definitions, format constraints, or business rules is quarantined "
        "with its original raw payload, failure reason, and rule code."
    )

    with get_db_session() as session:
        runs = session.query(PipelineRun).order_by(PipelineRun.start_time.desc()).all()
        quarantine = session.query(QuarantineRecord).order_by(QuarantineRecord.quarantined_at.desc()).limit(200).all()

    col_q1, col_q2 = st.columns(2)

    with col_q1:
        st.markdown("#### Pipeline Execution History")
        if runs:
            runs_data = [{
                "Run ID": r.run_id,
                "Status": r.status,
                "Start Time": str(r.start_time)[:19],
                "Duration (s)": r.duration_seconds,
                "Ingested": r.records_ingested,
                "Loaded": r.valid_records_loaded,
                "Quarantined": r.quarantined_records
            } for r in runs]
            st.dataframe(pd.DataFrame(runs_data), use_container_width=True, height=250)
        else:
            st.info("No pipeline runs recorded yet.")

    with col_q2:
        st.markdown("#### Quarantine Violation Breakdown")
        if quarantine:
            q_df = pd.DataFrame([{
                "rule_code": q.rule_code,
                "error_type": q.error_type,
                "source_system": q.source_system
            } for q in quarantine])

            rule_counts = q_df["rule_code"].value_counts().reset_index()
            rule_counts.columns = ["Rule Code", "Violations"]

            rule_chart = alt.Chart(rule_counts).mark_bar().encode(
                x=alt.X("Violations:Q"),
                y=alt.Y("Rule Code:N", sort="-x"),
                color=alt.value("#e03131"),
                tooltip=["Rule Code", "Violations"]
            ).properties(height=250)
            st.altair_chart(rule_chart, use_container_width=True)
        else:
            st.info("No quarantined records found.")

    st.markdown("#### Quarantined Records Inspector")
    if quarantine:
        q_inspect_df = pd.DataFrame([{
            "ID": q.id,
            "Record ID": q.record_id,
            "Source System": q.source_system,
            "Error Type": q.error_type,
            "Rule Code": q.rule_code,
            "Field": q.field_name,
            "Error Message": q.error_message,
            "Raw Payload Preview": q.raw_payload[:80] + "..." if len(q.raw_payload) > 80 else q.raw_payload
        } for q in quarantine])

        st.dataframe(q_inspect_df, use_container_width=True, height=280)


# -----------------------------------------------------------------------------
# TAB 5: Dimensional Warehouse Explorer
# -----------------------------------------------------------------------------
with tab5:
    st.subheader("🗄️ Dimensional Star Schema Explorer")

    table_choice = st.radio(
        "Select Warehouse Table to Inspect:",
        options=["dim_customers", "dim_products", "dim_date", "fact_orders", "fact_order_items"],
        horizontal=True
    )

    with get_db_session() as session:
        if table_choice == "dim_customers":
            records = session.query(DimCustomer).limit(100).all()
            df = pd.DataFrame([c.__dict__ for c in records]).drop(columns=["_sa_instance_state"], errors="ignore")
        elif table_choice == "dim_products":
            records = session.query(DimProduct).limit(100).all()
            df = pd.DataFrame([p.__dict__ for p in records]).drop(columns=["_sa_instance_state"], errors="ignore")
        elif table_choice == "dim_date":
            records = session.query(DimDate).limit(100).all()
            df = pd.DataFrame([d.__dict__ for d in records]).drop(columns=["_sa_instance_state"], errors="ignore")
        elif table_choice == "fact_orders":
            records = session.query(FactOrder).limit(100).all()
            df = pd.DataFrame([o.__dict__ for o in records]).drop(columns=["_sa_instance_state"], errors="ignore")
        elif table_choice == "fact_order_items":
            records = session.query(FactOrderItem).limit(100).all()
            df = pd.DataFrame([i.__dict__ for i in records]).drop(columns=["_sa_instance_state"], errors="ignore")

    st.markdown(f"**Showing preview for `{table_choice}` (up to 100 rows):**")
    st.dataframe(df, use_container_width=True, height=350)

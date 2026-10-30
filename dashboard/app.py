"""DataPulse operational monitoring and business analytics dashboard."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st
from sqlalchemy import func, select, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.analytics.queries import AnalyticsQueries
from app.warehouse.connection import check_database_connectivity, engine, get_db_session
from app.warehouse.models import (
    DimCustomer,
    DimDate,
    DimProduct,
    FactOrder,
    FactOrderItem,
    PipelineRun,
    QuarantineRecord,
)

st.set_page_config(
    page_title="DataPulse | Data Platform",
    page_icon="DP",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACCENT = "#16B8A6"
NAVY = "#122033"
CHART_COLORS = ["#16B8A6", "#4C7CF3", "#F2A541", "#8B6CE8", "#E76F51", "#5B718C"]
TABLES: dict[str, Any] = {
    "dim_customers": DimCustomer,
    "dim_products": DimProduct,
    "dim_date": DimDate,
    "fact_orders": FactOrder,
    "fact_order_items": FactOrderItem,
    "pipeline_runs": PipelineRun,
    "quarantine_records": QuarantineRecord,
}

st.markdown(
    """
    <style>
    :root { --dp-ink: #122033; --dp-muted: #607087; --dp-accent: #16B8A6; }
    .stApp { background: #f5f7fa; color: var(--dp-ink); }
    [data-testid="stMainBlockContainer"] { max-width: 1600px; padding-top: 2rem; }
    [data-testid="stSidebar"] { background: #101c2c; border-right: 1px solid #25354a; }
    [data-testid="stSidebar"] * { color: #e7edf5; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { padding: .18rem 0; }
    [data-testid="stSidebar"] [data-testid="stButton"] button {
        border: 1px solid #40536a; background: #18283c; color: white;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
        border-color: #16B8A6; color: #64e0d1;
    }
    .dp-brand { display:flex; align-items:center; gap: .7rem; margin:.2rem 0 .1rem; }
    .dp-mark {
        width:2.25rem; height:2.25rem; border-radius:.65rem; display:grid;
        place-items:center; color:#071e24; background:#16B8A6; font-weight:800;
        letter-spacing:-.08em;
    }
    .dp-name { color:#f4f7fb; font-weight:750; font-size:1.2rem; letter-spacing:-.03em; }
    .dp-caption { color:#9babc0; font-size:.78rem; margin:.15rem 0 1.25rem; }
    .dp-eyebrow { color:#64758b; font-size:.72rem; text-transform:uppercase;
        letter-spacing:.12em; font-weight:700; margin-bottom:.35rem; }
    .dp-subtitle { color:#607087; font-size:.91rem; margin-top:-.55rem; margin-bottom:1.35rem; }
    .dp-card {
        background:white; border:1px solid #e4e9ef; border-radius:.8rem;
        padding:1rem 1.1rem; min-height:6.25rem; box-shadow:0 2px 6px rgba(18,32,51,.025);
        overflow-wrap:anywhere;
    }
    .dp-card-label { color:#65758a; font-size:.78rem; font-weight:600; }
    .dp-card-value { color:#122033; font-size:1.55rem; font-weight:720;
        letter-spacing:-.04em; margin-top:.4rem; }
    .dp-card-note { color:#8290a1; font-size:.74rem; margin-top:.15rem; }
    div[data-testid="stMetric"] {
        background:white; border:1px solid #e4e9ef; padding:.9rem 1rem;
        border-radius:.8rem; box-shadow:0 2px 6px rgba(18,32,51,.025);
    }
    div[data-testid="stMetricLabel"] { color:#65758a; }
    h1, h2, h3 { letter-spacing:-.035em; color:#122033; }
    h1 { font-size:2rem !important; }
    h2 { font-size:1.35rem !important; }
    h3 { font-size:1rem !important; }
    [data-testid="stDataFrame"] { border:1px solid #e4e9ef; border-radius:.65rem; }
    [data-testid="stAlert"] { border-radius:.65rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _quarantine_rule_counts() -> pd.DataFrame:
    return _read_sql(
        select(
            QuarantineRecord.rule_code,
            func.count(QuarantineRecord.id).label("rejections"),
        )
        .group_by(QuarantineRecord.rule_code)
        .order_by(func.count(QuarantineRecord.id).desc())
    )


def _quarantine_category_counts() -> pd.DataFrame:
    return _read_sql(
        select(
            QuarantineRecord.error_type,
            QuarantineRecord.source_system,
            func.count(QuarantineRecord.id).label("records"),
        )
        .group_by(QuarantineRecord.error_type, QuarantineRecord.source_system)
        .order_by(func.count(QuarantineRecord.id).desc())
    )


def _read_sql(query: Any) -> pd.DataFrame:
    with engine.connect() as connection:
        return pd.read_sql(query, connection)


def _money(value: Any) -> str:
    return f"${float(value or 0):,.2f}"


def _empty(message: str) -> None:
    st.info(message, icon="ℹ️")


def _page_header(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="dp-eyebrow">DATAPULSE / {title.upper()}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="dp-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def _chart_theme(chart: alt.Chart, height: int = 310) -> alt.Chart:
    return (
        chart.properties(height=height)
        .configure_view(strokeOpacity=0)
        .configure_axis(
            labelColor="#718096",
            titleColor="#607087",
            gridColor="#edf1f5",
            domainColor="#dce3eb",
            tickColor="#dce3eb",
        )
        .configure_legend(labelColor="#607087", titleColor="#607087")
    )


def _metric_card(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f'<div class="dp-card"><div class="dp-card-label">{label}</div>'
        f'<div class="dp-card-value">{value}</div>'
        f'<div class="dp-card-note">{note}</div></div>',
        unsafe_allow_html=True,
    )


def _overview_values() -> dict[str, Any]:
    totals = _read_sql(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM dim_customers) AS total_customers,
                (SELECT COUNT(*) FROM fact_orders) AS total_orders,
                (SELECT COALESCE(SUM(net_amount), 0) FROM fact_orders
                    WHERE status = 'COMPLETED') AS total_revenue,
                (SELECT COALESCE(AVG(net_amount), 0) FROM fact_orders
                    WHERE status = 'COMPLETED') AS average_order_value
            """
        )
    )
    latest = _read_sql(
        select(
            PipelineRun.run_id,
            PipelineRun.status,
            PipelineRun.start_time,
            PipelineRun.duration_seconds,
        )
        .order_by(PipelineRun.start_time.desc())
        .limit(1)
    )
    result = totals.iloc[0].to_dict()
    result["latest_run"] = latest.iloc[0].to_dict() if not latest.empty else None
    return result


def _pipeline_runs(limit: int = 250) -> pd.DataFrame:
    return _read_sql(
        select(PipelineRun)
        .order_by(PipelineRun.start_time.desc())
        .limit(limit)
    )


def _quality_metrics() -> dict[str, Any]:
    aggregates = _read_sql(
        select(
            func.coalesce(func.sum(PipelineRun.records_ingested), 0).label("input"),
            func.coalesce(func.sum(PipelineRun.valid_records_loaded), 0).label("valid"),
            func.coalesce(func.sum(PipelineRun.quarantined_records), 0).label("rejected"),
        )
    ).iloc[0].to_dict()
    total = int(aggregates["valid"] or 0) + int(aggregates["rejected"] or 0)
    aggregates["quality_pct"] = (
        (float(aggregates["valid"]) / total * 100) if total else 0.0
    )
    return aggregates


def _quarantine_df(limit: int = 500) -> pd.DataFrame:
    return _read_sql(
        select(QuarantineRecord)
        .order_by(QuarantineRecord.quarantined_at.desc())
        .limit(limit)
    )


def _warehouse_preview(table_name: str, limit: int = 500) -> pd.DataFrame:
    model = TABLES[table_name]
    with get_db_session() as session:
        rows = session.execute(select(model).limit(limit)).scalars().all()
        return pd.DataFrame(
            [{column.key: getattr(row, column.key) for column in model.__table__.columns} for row in rows]
        )


def _api_health() -> tuple[bool, str]:
    url = f"{settings.APP_API_BASE_URL.rstrip('/')}/health"
    try:
        response = requests.get(url, timeout=2.5)
        response.raise_for_status()
        data = response.json()
        return True, f"{data.get('service', 'Application API')} · {data.get('status', 'healthy')}"
    except requests.RequestException as exc:
        return False, f"Application API is not reachable at {url}: {exc}"
    except (ValueError, KeyError) as exc:
        return False, f"Application API returned an unreadable health response: {exc}"


def _database_counts() -> dict[str, int]:
    with get_db_session() as session:
        return {
            table: int(session.scalar(select(func.count()).select_from(model)) or 0)
            for table, model in TABLES.items()
        }


def _explorer_search(df: pd.DataFrame, search: str, column: str, value: str) -> pd.DataFrame:
    filtered = df
    if column != "All columns" and value != "All values":
        filtered = filtered[filtered[column].astype(str) == value]
    if search.strip():
        query = search.strip().casefold()
        matches = filtered.astype(str).apply(
            lambda series: series.str.casefold().str.contains(query, regex=False, na=False)
        )
        filtered = filtered[matches.any(axis=1)]
    return filtered


with st.sidebar:
    st.markdown(
        '<div class="dp-brand"><div class="dp-mark">DP</div>'
        '<div class="dp-name">DataPulse</div></div>'
        '<div class="dp-caption">Data platform observability</div>',
        unsafe_allow_html=True,
    )
    st.markdown("NAVIGATION")
    section = st.radio(
        "Dashboard sections",
        [
            "Overview",
            "Pipeline Monitoring",
            "Data Quality",
            "Business Analytics",
            "Data Explorer",
            "System Health",
        ],
        label_visibility="collapsed",
        key="dashboard_section",
    )
    st.divider()
    st.caption(f"ENVIRONMENT  ·  {settings.APP_ENV.upper()}")
    st.caption(f"WAREHOUSE  ·  {engine.dialect.name.upper()}")
    if st.button("Refresh dashboard", use_container_width=True):
        st.rerun()
    if st.button("Run pipeline", type="primary", use_container_width=True):
        api_url = f"{settings.APP_API_BASE_URL.rstrip('/')}/api/v1/pipeline/run"
        try:
            with st.spinner("Running the DataPulse pipeline…"):
                response = requests.post(api_url, json={}, timeout=180)
                response.raise_for_status()
            run_result = response.json()
            st.session_state["last_triggered_run"] = run_result
            st.success(f"Run {run_result['run_id']} completed: {run_result['status']}")
            st.rerun()
        except requests.RequestException as exc:
            st.error(f"Could not trigger the pipeline through the application API: {exc}")
        except (ValueError, KeyError) as exc:
            st.error(f"The application API returned an invalid pipeline response: {exc}")
    st.markdown("---")
    st.caption("Live warehouse data · Auto-refresh on navigation")


overview: dict[str, Any] = {}
overview_error: str | None = None
if section in {"Overview", "System Health"}:
    try:
        with st.spinner("Loading warehouse data…"):
            overview = _overview_values()
    except Exception as exc:
        overview_error = str(exc)


if section == "Overview":
    _page_header(
        "Overview",
        "A live view of warehouse performance, commercial outcomes, and the most recent pipeline activity.",
    )
    if overview_error:
        st.error(f"Unable to load overview metrics from the warehouse: {overview_error}")
        st.stop()
    run = overview["latest_run"]
    latest_status = str(run["status"]) if run else "No runs"
    latest_note = (
        f"{run['run_id']} · {run['start_time']:%Y-%m-%d %H:%M}"
        if run and isinstance(run["start_time"], datetime)
        else (str(run["run_id"]) if run else "Trigger a run to start monitoring")
    )
    columns = st.columns(4)
    cards = [
        ("Customers", f"{int(overview['total_customers']):,}", "Customer dimension"),
        ("Orders", f"{int(overview['total_orders']):,}", "All warehouse orders"),
        ("Net revenue", _money(overview["total_revenue"]), "Completed orders"),
        ("Average order value", _money(overview["average_order_value"]), "Completed orders"),
    ]
    for column, (label, value, note) in zip(columns, cards):
        with column:
            _metric_card(label, value, note)

    st.subheader("Latest pipeline execution")
    if run:
        run_columns = st.columns([1, 2, 1, 1])
        run_columns[0].metric("Status", latest_status)
        run_columns[1].caption("Run ID")
        run_columns[1].code(str(run["run_id"]), language=None)
        run_columns[2].metric(
            "Duration",
            f"{float(run['duration_seconds'] or 0):.2f} sec",
        )
        run_columns[3].caption("Started")
        run_columns[3].write(
            run["start_time"].strftime("%Y-%m-%d %H:%M")
            if isinstance(run["start_time"], datetime)
            else str(run["start_time"])
        )
    else:
        _empty("No pipeline runs are recorded yet. Use Run pipeline in the sidebar to start a run.")

    left, right = st.columns([1.55, 1])
    try:
        trends = AnalyticsQueries(engine).get_monthly_revenue_trends()
    except Exception as exc:
        trends = pd.DataFrame()
        st.warning(f"Monthly revenue trends are unavailable: {exc}")
    with left:
        st.subheader("Monthly revenue")
        st.caption("Revenue and average order value include completed orders; order counts include all statuses.")
        if trends.empty:
            _empty("Revenue trends will appear after completed orders are loaded.")
        else:
            chart = alt.Chart(trends).mark_line(
                point=alt.OverlayMarkDef(filled=True, size=48), strokeWidth=2.5
            ).encode(
                x=alt.X("year_month:N", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("net_revenue:Q", title="Net revenue ($)", scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip("year_month:N", title="Month"),
                    alt.Tooltip("net_revenue:Q", title="Revenue", format=",.2f"),
                    alt.Tooltip("completed_orders:Q", title="Completed orders"),
                ],
                color=alt.value(ACCENT),
            )
            st.altair_chart(_chart_theme(chart, 300), use_container_width=True)
    with right:
        st.subheader("Warehouse overview")
        try:
            counts = _database_counts()
            st.caption(
                f"{counts['dim_customers']:,} customers · {counts['dim_products']:,} products · "
                f"{counts['fact_orders']:,} orders"
            )
        except Exception as exc:
            st.error(f"Could not read warehouse table counts: {exc}")

    st.subheader("Recent pipeline activity")
    try:
        runs_df = _pipeline_runs(8)
        if runs_df.empty:
            _empty("There is no run history to show.")
        else:
            st.dataframe(
                runs_df[
                    [
                        "run_id",
                        "status",
                        "start_time",
                        "duration_seconds",
                        "records_ingested",
                        "valid_records_loaded",
                        "quarantined_records",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
    except Exception as exc:
        st.error(f"Unable to load recent pipeline activity: {exc}")


elif section == "Pipeline Monitoring":
    _page_header(
        "Pipeline Monitoring",
        "Track run outcomes, processing volume, execution time, and run-level audit details.",
    )
    try:
        runs = _pipeline_runs()
        if runs.empty:
            _empty("No pipeline runs are recorded. Use Run pipeline in the sidebar to create the first run.")
        else:
            normalized_status = runs["status"].astype(str).str.upper()
            success_count = int(normalized_status.eq("SUCCESS").sum())
            partial_count = int(normalized_status.eq("PARTIAL_SUCCESS").sum())
            failed_count = int(runs["status"].astype(str).str.upper().eq("FAILED").sum())
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Recorded runs", f"{len(runs):,}")
            c2.metric("Successful", f"{success_count:,}")
            c3.metric("Partial success", f"{partial_count:,}")
            c4.metric("Failed", f"{failed_count:,}")
            c5.metric(
                "Average duration",
                f"{runs['duration_seconds'].dropna().mean():.2f} sec"
                if runs["duration_seconds"].notna().any()
                else "—",
            )

            st.subheader("Run history")
            history = runs.copy()
            history["start_time"] = pd.to_datetime(history["start_time"])
            history_chart = alt.Chart(history).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("start_time:T", title="Run start"),
                y=alt.Y("duration_seconds:Q", title="Duration (seconds)"),
                color=alt.Color(
                    "status:N",
                    scale=alt.Scale(
                        domain=["SUCCESS", "PARTIAL_SUCCESS", "FAILED"],
                        range=[ACCENT, "#F2A541", "#D84A4A"],
                    ),
                    legend=alt.Legend(title="Status"),
                ),
                tooltip=["run_id:N", "status:N", "duration_seconds:Q", "records_ingested:Q"],
            )
            st.altair_chart(_chart_theme(history_chart, 250), use_container_width=True)

            st.subheader("Run records")
            st.dataframe(
                runs[
                    [
                        "run_id",
                        "pipeline_name",
                        "status",
                        "start_time",
                        "end_time",
                        "duration_seconds",
                        "records_ingested",
                        "valid_records_loaded",
                        "quarantined_records",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
            selected_run = st.selectbox("Inspect a run", runs["run_id"].astype(str).tolist())
            details = runs.loc[runs["run_id"].astype(str) == selected_run].iloc[0]
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Input records", f"{int(details['records_ingested'] or 0):,}")
            i2.metric("Output records", f"{int(details['valid_records_loaded'] or 0):,}")
            i3.metric("Rejected records", f"{int(details['quarantined_records'] or 0):,}")
            i4.metric(
                "Duration",
                f"{float(details['duration_seconds'] or 0):.2f} sec",
            )
            with st.expander("Run metadata", expanded=False):
                st.write(
                    {
                        "run_id": selected_run,
                        "pipeline_name": details["pipeline_name"],
                        "status": details["status"],
                        "started": str(details["start_time"]),
                        "finished": str(details["end_time"]),
                    }
                )
                if details.get("details_json"):
                    try:
                        st.json(json.loads(details["details_json"]))
                    except (TypeError, json.JSONDecodeError):
                        st.code(str(details["details_json"]))
            try:
                details_payload = json.loads(details["details_json"] or "{}")
                phase_durations = details_payload.get("phase_durations", {})
                phase_rows = [
                    {
                        "phase": (
                            phase.split("_", 1)[1]
                            if phase.partition("_")[0].isdigit()
                            else phase
                        ).replace("_", " ").title(),
                        "duration_seconds": float(duration),
                    }
                    for phase, duration in phase_durations.items()
                    if duration is not None and float(duration) > 0
                ]
                st.subheader("Recorded phase durations")
                if phase_rows:
                    phase_data = pd.DataFrame(phase_rows)
                    phase_chart = alt.Chart(phase_data).mark_bar(
                        cornerRadiusEnd=3,
                        color=ACCENT,
                    ).encode(
                        x=alt.X("duration_seconds:Q", title="Duration (seconds)"),
                        y=alt.Y("phase:N", title=None, sort="-x"),
                        tooltip=[
                            alt.Tooltip("phase:N", title="Pipeline phase"),
                            alt.Tooltip("duration_seconds:Q", title="Duration", format=".4f"),
                        ],
                    )
                    st.altair_chart(_chart_theme(phase_chart, 240), use_container_width=True)
                    st.caption("Only phases with a recorded duration are shown.")
                else:
                    _empty("No phase-duration metrics were recorded for this run.")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                st.warning(f"Phase timing details are unavailable for this run: {exc}")
    except Exception as exc:
        st.error(f"Pipeline history could not be loaded: {exc}")


elif section == "Data Quality":
    _page_header(
        "Data Quality",
        "Measure ingestion quality and inspect rejected records alongside their validation rules.",
    )
    try:
        metrics = _quality_metrics()
        a, b, c, d = st.columns(4)
        a.metric("Data quality", f"{metrics['quality_pct']:.1f}%")
        b.metric("Input records", f"{int(metrics['input']):,}")
        c.metric("Valid records", f"{int(metrics['valid']):,}")
        d.metric("Rejected records", f"{int(metrics['rejected']):,}")

        valid_rejected = pd.DataFrame(
            [
                {"Record outcome": "Valid", "Records": int(metrics["valid"])},
                {"Record outcome": "Rejected", "Records": int(metrics["rejected"])},
            ]
        )
        chart_col, distribution_col = st.columns([1, 1.25])
        with chart_col:
            st.subheader("Valid versus rejected")
            if int(metrics["valid"]) + int(metrics["rejected"]) == 0:
                _empty("Quality metrics will be available after the first pipeline run.")
            else:
                chart = alt.Chart(valid_rejected).mark_arc(innerRadius=65).encode(
                    theta=alt.Theta("Records:Q"),
                    color=alt.Color(
                        "Record outcome:N",
                        scale=alt.Scale(domain=["Valid", "Rejected"], range=[ACCENT, "#D84A4A"]),
                    ),
                    tooltip=["Record outcome:N", "Records:Q"],
                )
                st.altair_chart(_chart_theme(chart, 300), use_container_width=True)
        with distribution_col:
            st.subheader("Validation violations by rule")
            rule_counts = _quarantine_rule_counts()
            if rule_counts.empty:
                _empty("No quarantined records are currently available.")
            else:
                chart = alt.Chart(rule_counts).mark_bar(cornerRadiusEnd=3).encode(
                    x=alt.X("rejections:Q", title="Violation entries"),
                    y=alt.Y("rule_code:N", title="Validation rule", sort="-x"),
                    color=alt.value("#D84A4A"),
                    tooltip=["rule_code:N", "rejections:Q"],
                )
                st.altair_chart(_chart_theme(chart, 300), use_container_width=True)

        st.subheader("Rejection categories")
        categories = _quarantine_category_counts()
        if not categories.empty:
            st.dataframe(categories, use_container_width=True, hide_index=True)

        st.subheader("Quarantine entries")
        quarantines = _quarantine_df()
        if quarantines.empty:
            _empty("Rejected record details will appear here when the pipeline quarantines data.")
        else:
            st.caption(
                "Latest 500 rejection reasons. A source record can have multiple entries "
                "when it fails more than one validation rule."
            )
            all_runs = ["All runs"] + sorted(
                quarantines["run_id"].dropna().astype(str).unique().tolist(), reverse=True
            )
            chosen_run = st.selectbox("Filter by pipeline run", all_runs)
            view = quarantines if chosen_run == "All runs" else quarantines[
                quarantines["run_id"].astype(str) == chosen_run
            ]
            st.dataframe(
                view[
                    [
                        "quarantined_at",
                        "run_id",
                        "record_id",
                        "source_system",
                        "error_type",
                        "rule_code",
                        "field_name",
                        "error_message",
                        "raw_payload",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                height=360,
            )
    except Exception as exc:
        st.error(f"Data quality information could not be loaded: {exc}")


elif section == "Business Analytics":
    _page_header(
        "Business Analytics",
        "Explore revenue performance, product sales, customer cohorts, geography, and order fulfillment.",
    )
    try:
        queries = AnalyticsQueries(engine)
        trends = queries.get_monthly_revenue_trends()
        if trends.empty:
            _empty("Business analytics will appear once orders have been loaded into the warehouse.")
        else:
            revenue_col, monthly_col = st.columns([1.3, 1])
            with revenue_col:
                st.subheader("Revenue trend")
                line = alt.Chart(trends).mark_line(
                    point=alt.OverlayMarkDef(filled=True, size=45), strokeWidth=2.5
                ).encode(
                    x=alt.X("year_month:N", title="Month", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("net_revenue:Q", title="Net revenue ($)"),
                    color=alt.value(ACCENT),
                    tooltip=["year_month:N", "net_revenue:Q", "gross_revenue:Q", "completed_orders:Q"],
                )
                st.altair_chart(_chart_theme(line, 290), use_container_width=True)
            with monthly_col:
                st.subheader("Monthly performance")
                cols = [
                    name for name in [
                        "year_month",
                        "total_orders",
                        "completed_orders",
                        "gross_revenue",
                        "net_revenue",
                        "average_order_value",
                        "mom_growth_pct",
                    ] if name in trends.columns
                ]
                st.dataframe(
                    trends[cols].sort_values("year_month", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                    height=290,
                )

            products_col, segments_col = st.columns(2)
            products = queries.get_top_products_performance(limit=12)
            with products_col:
                st.subheader("Top products")
                if products.empty:
                    _empty("Product performance will appear after order items are loaded.")
                else:
                    product_chart = alt.Chart(products).mark_bar(cornerRadiusEnd=3).encode(
                        x=alt.X("net_sales:Q", title="Net sales ($)"),
                        y=alt.Y("product_name:N", sort="-x", title=None),
                        color=alt.Color("category:N", scale=alt.Scale(range=CHART_COLORS)),
                        tooltip=["product_name:N", "category:N", "total_units_sold:Q", "net_sales:Q"],
                    )
                    st.altair_chart(_chart_theme(product_chart, 340), use_container_width=True)
            with segments_col:
                st.subheader("Customer segmentation")
                rfm = queries.get_rfm_segmentation()
                if rfm.empty:
                    _empty("Customer segmentation requires customer and order data.")
                else:
                    segments = rfm.groupby("rfm_segment").size().reset_index(name="customers")
                    segment_chart = alt.Chart(segments).mark_bar(cornerRadiusEnd=3).encode(
                        x=alt.X("customers:Q", title="Customers"),
                        y=alt.Y("rfm_segment:N", sort="-x", title=None),
                        color=alt.Color("rfm_segment:N", scale=alt.Scale(range=CHART_COLORS), legend=None),
                        tooltip=["rfm_segment:N", "customers:Q"],
                    )
                    st.altair_chart(_chart_theme(segment_chart, 340), use_container_width=True)

            geo_query = text(
                """
                SELECT c.state, COUNT(DISTINCT o.order_key) AS orders,
                       ROUND(COALESCE(SUM(o.net_amount), 0), 2) AS revenue
                FROM dim_customers c
                JOIN fact_orders o ON o.customer_key = c.customer_key
                WHERE o.status = 'COMPLETED'
                GROUP BY c.state
                ORDER BY revenue DESC
                """
            )
            geo = _read_sql(geo_query)
            status = _read_sql(
                select(FactOrder.status.label("status"), func.count(FactOrder.order_key).label("orders"))
                .group_by(FactOrder.status)
                .order_by(func.count(FactOrder.order_key).desc())
            )
            geo_col, status_col = st.columns(2)
            with geo_col:
                st.subheader("Geographic revenue distribution")
                if geo.empty:
                    _empty("Geographic revenue is not available yet.")
                else:
                    geo_chart = alt.Chart(geo.head(15)).mark_bar(cornerRadiusEnd=3).encode(
                        x=alt.X("revenue:Q", title="Revenue ($)"),
                        y=alt.Y("state:N", title="Customer state", sort="-x"),
                        color=alt.value("#4C7CF3"),
                        tooltip=["state:N", "orders:Q", "revenue:Q"],
                    )
                    st.altair_chart(_chart_theme(geo_chart, 330), use_container_width=True)
            with status_col:
                st.subheader("Order-status breakdown")
                if status.empty:
                    _empty("Order-status counts will appear when orders are loaded.")
                else:
                    status_chart = alt.Chart(status).mark_arc(innerRadius=60).encode(
                        theta=alt.Theta("orders:Q"),
                        color=alt.Color("status:N", scale=alt.Scale(range=CHART_COLORS)),
                        tooltip=["status:N", "orders:Q"],
                    )
                    st.altair_chart(_chart_theme(status_chart, 330), use_container_width=True)
                    st.dataframe(status, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Business analytics could not be loaded: {exc}")


elif section == "Data Explorer":
    _page_header(
        "Data Explorer",
        "Search warehouse records, inspect schema table volumes, and view analytical query outputs.",
    )
    try:
        counts = _database_counts()
        st.subheader("Warehouse inventory")
        inventory = pd.DataFrame(
            [{"table": table, "records": count} for table, count in counts.items()]
        )
        st.dataframe(inventory, use_container_width=True, hide_index=True)

        st.subheader("Search and filter records")
        table_name = st.selectbox("Warehouse table", list(TABLES.keys()))
        with st.spinner(f"Loading {table_name}…"):
            df = _warehouse_preview(table_name)
        if df.empty:
            _empty(f"The `{table_name}` table is empty.")
        else:
            filters = st.columns([1, 1, 2])
            categorical = [
                name for name in df.columns
                if df[name].nunique(dropna=True) <= 40 and df[name].nunique(dropna=True) > 1
            ]
            with filters[0]:
                filter_column = st.selectbox("Filter column", ["All columns"] + categorical)
            with filters[1]:
                if filter_column == "All columns":
                    filter_value = "All values"
                    st.selectbox("Filter value", ["All values"], disabled=True)
                else:
                    value_options = sorted(df[filter_column].dropna().astype(str).unique().tolist())
                    filter_value = st.selectbox("Filter value", ["All values"] + value_options)
            with filters[2]:
                search = st.text_input("Search loaded records", placeholder="Search any displayed field…")
            filtered = _explorer_search(df, search, filter_column, filter_value)
            st.caption(f"Showing {len(filtered):,} of {len(df):,} loaded rows (maximum preview: 500).")
            if filtered.empty:
                _empty("No records match the current search and filter.")
            else:
                st.dataframe(filtered, use_container_width=True, hide_index=True, height=400)

        st.subheader("Analytical query results")
        query_choice = st.selectbox(
            "Choose a warehouse analysis",
            [
                "Monthly revenue trends",
                "Top product performance",
                "Customer segmentation (RFM)",
                "Customer lifetime value by segment",
                "Category breakdown",
            ],
        )
        analytics = AnalyticsQueries(engine)
        query_map = {
            "Monthly revenue trends": analytics.get_monthly_revenue_trends,
            "Top product performance": analytics.get_top_products_performance,
            "Customer segmentation (RFM)": analytics.get_rfm_segmentation,
            "Customer lifetime value by segment": analytics.get_customer_clv_by_segment,
            "Category breakdown": analytics.get_category_breakdown,
        }
        with st.spinner("Running analytical query…"):
            result = query_map[query_choice]()
        if result.empty:
            _empty(f"No rows are available for {query_choice.lower()}.")
        else:
            st.dataframe(result, use_container_width=True, hide_index=True, height=330)
    except Exception as exc:
        st.error(f"Data explorer query failed: {exc}")


else:
    _page_header(
        "System Health",
        "Monitor API availability, warehouse connectivity, and recent pipeline execution statistics.",
    )
    api_ok, api_message = _api_health()
    db_status = check_database_connectivity(engine)
    latest = overview.get("latest_run")
    latest_ok = latest is not None and str(latest["status"]).upper() in {"SUCCESS", "PARTIAL_SUCCESS"}
    api_col, db_col, run_col = st.columns(3)
    with api_col:
        st.subheader("Application API")
        if api_ok:
            st.success(api_message)
        else:
            st.error(api_message)
    with db_col:
        st.subheader("Warehouse database")
        if db_status.get("connected"):
            st.success(
                f"Connected · {db_status.get('dialect', 'unknown').upper()} · "
                f"{db_status.get('ping_latency_ms', 0):.2f} ms"
            )
        else:
            st.error(f"Database connection failed: {db_status.get('error', 'unknown error')}")
    with run_col:
        st.subheader("Latest execution")
        if overview_error:
            st.error(f"Latest execution status is unavailable: {overview_error}")
        elif latest:
            if latest_ok:
                st.success(f"{latest['status']} · {latest['run_id']}")
            else:
                st.error(f"{latest['status']} · {latest['run_id']}")
            st.caption(f"Started {latest['start_time']}")
        else:
            _empty("No pipeline execution has been recorded.")

    st.subheader("Pipeline execution statistics")
    try:
        runs = _pipeline_runs()
        if runs.empty:
            _empty("Execution statistics will appear once pipeline runs are recorded.")
        else:
            run_status = (
                runs["status"].astype(str).str.upper().value_counts().rename_axis("status")
                .reset_index(name="runs")
            )
            stats = st.columns(4)
            stats[0].metric("Total executions", f"{len(runs):,}")
            stats[1].metric(
                "Successful",
                f"{int(runs['status'].astype(str).str.upper().isin(['SUCCESS', 'PARTIAL_SUCCESS']).sum()):,}",
            )
            stats[2].metric(
                "Failed",
                f"{int(runs['status'].astype(str).str.upper().eq('FAILED').sum()):,}",
            )
            mean_duration = runs["duration_seconds"].dropna().mean()
            stats[3].metric(
                "Mean duration",
                f"{mean_duration:.2f} sec" if pd.notna(mean_duration) else "—",
            )
            st.dataframe(run_status, use_container_width=True, hide_index=True)
            st.caption(f"Last checked at {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}")
    except Exception as exc:
        st.error(f"Pipeline execution statistics are unavailable: {exc}")

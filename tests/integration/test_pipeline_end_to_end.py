"""Deterministic end-to-end pipeline tests using an isolated warehouse."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.pipeline import DataPulsePipeline
from app.warehouse.models import (
    DimCustomer,
    DimDate,
    FactOrder,
    FactOrderItem,
    PipelineRun,
    QuarantineRecord,
)


def _pipeline(
    csv_path: Path,
    configure_mock_source,
    source_orders: list[dict],
) -> DataPulsePipeline:
    configure_mock_source(source_orders)
    return DataPulsePipeline(csv_path=csv_path, force_mock_api_client=True)


def test_complete_pipeline_persists_facts_quality_and_audit_records(
    tmp_path: Path,
    write_customer_csv,
    sample_valid_customer,
    sample_valid_order,
    configure_mock_source,
    test_db_session: Session,
):
    csv_path = write_customer_csv(tmp_path / "customers.csv", [sample_valid_customer])
    pipeline = _pipeline(csv_path, configure_mock_source, [sample_valid_order])

    result = pipeline.run()

    assert result.status == "SUCCESS"
    assert result.total_ingested == 2, "Pipeline should ingest the customer and API order."
    assert result.total_loaded == 2, "One customer and one order should load."
    assert result.total_quarantined == 0
    run = test_db_session.get(PipelineRun, result.run_id)
    assert run is not None, "Successful execution must persist a pipeline audit record."
    assert run.status == "SUCCESS"
    assert run.records_ingested == 2
    assert test_db_session.scalar(select(func.count()).select_from(DimCustomer)) == 1
    assert test_db_session.scalar(select(func.count()).select_from(FactOrder)) == 1
    assert test_db_session.scalar(select(func.count()).select_from(FactOrderItem)) == 2
    assert test_db_session.scalar(select(func.count()).select_from(QuarantineRecord)) == 0


def test_empty_input_batch_completes_without_fact_rows(
    tmp_path: Path,
    configure_mock_source,
    test_db_session: Session,
):
    csv_path = tmp_path / "empty-customers.csv"
    csv_path.write_text(
        "customer_id,first_name,last_name,email,city,state,postal_code,signup_date\n",
        encoding="utf-8",
    )
    pipeline = _pipeline(csv_path, configure_mock_source, [])

    result = pipeline.run()

    assert result.status == "SUCCESS", "An empty batch should be a valid no-op run."
    assert result.total_ingested == 0
    assert result.total_loaded == 0
    assert test_db_session.scalar(select(func.count()).select_from(FactOrder)) == 0
    assert test_db_session.get(PipelineRun, result.run_id) is not None


def test_identical_pipeline_input_is_idempotent(
    tmp_path: Path,
    write_customer_csv,
    sample_valid_customer,
    sample_valid_order,
    configure_mock_source,
    test_db_session: Session,
):
    csv_path = write_customer_csv(tmp_path / "customers.csv", [sample_valid_customer])
    pipeline = _pipeline(csv_path, configure_mock_source, [sample_valid_order])

    first = pipeline.run()
    initial_counts = (
        test_db_session.scalar(select(func.count()).select_from(DimCustomer)),
        test_db_session.scalar(select(func.count()).select_from(FactOrder)),
        test_db_session.scalar(select(func.count()).select_from(FactOrderItem)),
    )
    second = pipeline.run()
    repeated_counts = (
        test_db_session.scalar(select(func.count()).select_from(DimCustomer)),
        test_db_session.scalar(select(func.count()).select_from(FactOrder)),
        test_db_session.scalar(select(func.count()).select_from(FactOrderItem)),
    )

    assert first.run_id != second.run_id
    assert repeated_counts == initial_counts == (1, 1, 2), (
        "Replaying an identical source batch must not duplicate warehouse facts."
    )


def test_pipeline_retry_after_transient_load_failure_does_not_duplicate_rows(
    tmp_path: Path,
    write_customer_csv,
    sample_valid_customer,
    sample_valid_order,
    configure_mock_source,
    test_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    csv_path = write_customer_csv(tmp_path / "customers.csv", [sample_valid_customer])
    pipeline = _pipeline(csv_path, configure_mock_source, [sample_valid_order])
    load_orders = pipeline.loader.load_orders_and_items
    attempts = 0

    def fail_once_then_load(session, orders, items):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("injected transient load failure")
        return load_orders(session, orders, items)

    monkeypatch.setattr(pipeline.loader, "load_orders_and_items", fail_once_then_load)
    with pytest.raises(RuntimeError, match="transient load failure"):
        pipeline.run()

    result = pipeline.run()

    assert result.status == "SUCCESS", "Retry should complete after the transient failure."
    assert attempts == 2
    assert test_db_session.scalar(select(func.count()).select_from(DimCustomer)) == 1
    assert test_db_session.scalar(select(func.count()).select_from(FactOrder)) == 1
    assert test_db_session.scalar(select(func.count()).select_from(FactOrderItem)) == 2
    assert test_db_session.scalar(select(func.count()).select_from(PipelineRun)) == 1


def test_pipeline_loads_late_arriving_historical_order(
    tmp_path: Path,
    write_customer_csv,
    sample_valid_customer,
    sample_valid_order,
    configure_mock_source,
    test_db_session: Session,
):
    csv_path = write_customer_csv(tmp_path / "customers.csv", [sample_valid_customer])
    recent_order = deepcopy(sample_valid_order)
    recent_order["order_id"] = "ORD-RECENT"
    recent_order["order_timestamp"] = "2025-06-15T10:00:00Z"
    _pipeline(csv_path, configure_mock_source, [recent_order]).run()

    late_order = deepcopy(sample_valid_order)
    late_order["order_timestamp"] = "2023-11-20T14:30:00Z"
    result = _pipeline(csv_path, configure_mock_source, [late_order]).run()

    assert result.status == "SUCCESS"
    assert test_db_session.scalar(select(func.count()).select_from(FactOrder)) == 2
    assert test_db_session.get(DimDate, 20231120) is not None, (
        "A record arriving after a newer run must still add its historical date dimension."
    )
    assert test_db_session.get(DimDate, 20250615) is not None

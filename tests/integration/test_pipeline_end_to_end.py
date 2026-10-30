"""
End-to-End Integration Tests for DataPulse Pipeline.
"""

from __future__ import annotations

from app.pipeline import DataPulsePipeline
from app.warehouse.connection import get_db_session
from app.warehouse.models import DimCustomer, FactOrder, PipelineRun, QuarantineRecord


def test_end_to_end_pipeline_execution():
    pipeline = DataPulsePipeline(force_mock_api_client=True)
    result = pipeline.run()

    assert result.status == "SUCCESS"
    assert result.duration_seconds > 0.0
    assert result.total_ingested > 0
    assert result.total_loaded > 0
    assert result.total_quarantined > 0

    with get_db_session() as session:
        cust_count = session.query(DimCustomer).count()
        order_count = session.query(FactOrder).count()
        quarantine_count = session.query(QuarantineRecord).count()
        run_record = session.query(PipelineRun).filter_by(run_id=result.run_id).first()

        assert cust_count > 0
        assert order_count > 0
        assert quarantine_count > 0
        assert run_record is not None
        assert run_record.status == "SUCCESS"
        assert run_record.records_ingested == result.total_ingested

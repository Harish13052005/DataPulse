"""
Integration Test for Database Connectivity and Health Check Diagnostic.
"""

from __future__ import annotations

from sqlalchemy import create_engine

from app.warehouse.connection import check_database_connectivity


def test_isolated_test_database_responds_to_connectivity_ping(test_engine):
    """Verify connectivity without opening the configured application database."""
    result = check_database_connectivity(test_engine)
    assert result["connected"] is True
    assert result["status"] == "healthy"
    assert "dialect" in result
    assert result["ping_latency_ms"] >= 0.0


def test_missing_database_path_returns_unhealthy_diagnostic(tmp_path):
    unavailable_engine = create_engine(
        f"sqlite:///{tmp_path / 'missing-directory' / 'unavailable.sqlite'}"
    )
    try:
        result = check_database_connectivity(unavailable_engine)
    finally:
        unavailable_engine.dispose()

    assert result["connected"] is False
    assert result["status"] == "unhealthy"
    assert "error" in result, "Connection failures must expose a diagnostic error."

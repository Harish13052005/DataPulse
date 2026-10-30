"""
Integration Test for Database Connectivity and Health Check Diagnostic.
"""

from __future__ import annotations

from app.warehouse.connection import check_database_connectivity, engine


def test_database_connectivity_live():
    """Verify live database responds to connectivity ping."""
    result = check_database_connectivity(engine)
    assert result["connected"] is True
    assert result["status"] == "healthy"
    assert "dialect" in result
    assert result["ping_latency_ms"] >= 0.0

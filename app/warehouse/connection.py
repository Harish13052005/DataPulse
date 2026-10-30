"""
DataPulse Warehouse Database Connection & Session Factory.

Configures SQLAlchemy 2.0 engine, connection pool, and scoped session generator.
Seamlessly handles PostgreSQL 16 (with connection pooling) and SQLite local fallback.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config.settings import settings
from app.monitoring.logger import get_logger

logger = get_logger("datapulse.warehouse")
Base = declarative_base()


def create_db_engine(database_url: str | None = None) -> Engine:
    """
    Create and configure SQLAlchemy engine.
    - PostgreSQL: connection pooling (pool_size=10, max_overflow=20, pool_pre_ping=True).
    - SQLite: WAL mode and foreign key enforcement.
    """
    url = database_url or settings.DATABASE_URL
    is_sqlite = url.startswith("sqlite")

    connect_args: Dict[str, Any] = {}
    engine_kwargs: Dict[str, Any] = {
        "echo": settings.DB_ECHO,
        "pool_pre_ping": True,
    }

    if is_sqlite:
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args
    else:
        # Production PostgreSQL pooling parameters
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20
        engine_kwargs["pool_recycle"] = 1800

    engine = create_engine(url, **engine_kwargs)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


# Default application engine and sessionmaker
engine = create_db_engine()
SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
# Compatibility alias for the original loader entry point.
SessionLocal = SessionFactory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provide a transactional database session scope."""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Database session rolled back due to error: {exc}")
        raise
    finally:
        session.close()


def check_database_connectivity(custom_engine: Engine | None = None) -> Dict[str, Any]:
    """
    Verify database connectivity and measure query latency.
    Returns diagnostic details: status, dialect, database name, and ping latency (ms).
    """
    target_engine = custom_engine or engine
    start_time = time.perf_counter()

    try:
        with target_engine.connect() as conn:
            # Query version or 1 based on dialect
            result = conn.execute(text("SELECT 1")).scalar()
            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            dialect_name = target_engine.dialect.name
            db_name = target_engine.url.database or "in-memory"

            return {
                "status": "healthy",
                "connected": True,
                "dialect": dialect_name,
                "database": db_name,
                "ping_latency_ms": latency_ms,
                "result": result
            }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        logger.error(f"Database connectivity check failed: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "dialect": target_engine.dialect.name if hasattr(target_engine, "dialect") else "unknown",
            "error": str(e),
            "ping_latency_ms": latency_ms
        }

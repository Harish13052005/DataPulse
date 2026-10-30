"""
DataPulse Centralized Configuration Module.

Loads environment variables with strict typing, directory resolution,
and defaults for development, testing, and production environments.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv

# Base Directory Resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=False)
else:
    # Fallback to .env.example defaults if .env not yet created
    EXAMPLE_ENV = PROJECT_ROOT / ".env.example"
    if EXAMPLE_ENV.exists():
        load_dotenv(dotenv_path=EXAMPLE_ENV, override=False)


class Settings:
    """Centralized Application Configuration."""

    # Application Metadata
    APP_NAME: str = os.getenv("APP_NAME", "DataPulse")
    APP_ENV: Literal["development", "test", "production"] = os.getenv("APP_ENV", "development")  # type: ignore
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Reproducibility Seed
    RANDOM_SEED: int = int(os.getenv("RANDOM_SEED", "42"))

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{PROJECT_ROOT / 'datapulse_warehouse.db'}"
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() in ("true", "1", "yes")

    # PostgreSQL Container Parameters
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "datapulse_dw")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "datapulse")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "datapulse_secure_pass")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))

    # Filesystem Paths
    BASE_DIR: Path = PROJECT_ROOT
    APP_DIR: Path = PROJECT_ROOT / "app"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    RAW_DATA_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
    SAMPLE_DATA_DIR: Path = DATA_DIR / "sample"
    QUARANTINE_DATA_DIR: Path = DATA_DIR / "quarantine"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    SQL_DIR: Path = PROJECT_ROOT / "sql"
    SCHEMA_DIR: Path = SQL_DIR / "schema"
    QUERIES_DIR: Path = SQL_DIR / "queries"

    # Ingestion Source 1: Customer CSV
    CUSTOMERS_CSV_PATH: Path = RAW_DATA_DIR / "customers.csv"

    # Ingestion Source 2: Mock Orders REST API
    API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_BASE_URL: str = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")
    APP_API_PORT: int = int(os.getenv("APP_API_PORT", "8001"))
    APP_API_BASE_URL: str = os.getenv(
        "APP_API_BASE_URL", f"http://{API_HOST}:{APP_API_PORT}"
    )
    API_TIMEOUT_SECONDS: float = float(os.getenv("API_TIMEOUT_SECONDS", "10.0"))
    API_PAGE_SIZE: int = int(os.getenv("API_PAGE_SIZE", "50"))

    # Pipeline Tuning
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "500"))
    RETRY_ATTEMPTS: int = int(os.getenv("RETRY_ATTEMPTS", "3"))
    RETRY_BACKOFF_FACTOR: float = float(os.getenv("RETRY_BACKOFF_FACTOR", "0.5"))
    INJECT_DIRTY_DATA_RATIO: float = float(os.getenv("INJECT_DIRTY_DATA_RATIO", "0.08"))

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required runtime directories exist."""
        cls.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.QUARANTINE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
        cls.QUERIES_DIR.mkdir(parents=True, exist_ok=True)


# Singleton instance
settings = Settings()
settings.ensure_directories()

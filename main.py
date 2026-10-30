"""
DataPulse Main Application Entrypoint & Health Check Service.

Usage:
    python main.py                   # Run application health check and system diagnostic
    python main.py --health          # Explicit health check
    python main.py --pipeline        # Trigger ELT pipeline execution
    python main.py --api             # Launch mock REST API server
    python main.py --dashboard       # Launch Streamlit dashboard
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Project root path resolution
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.monitoring.logger import get_logger
from app.warehouse.connection import check_database_connectivity

logger = get_logger("datapulse.main")


def run_health_check() -> dict:
    """
    Perform a complete application health check and environment audit.
    """
    print("\n" + "=" * 70)
    print(f"  {settings.APP_NAME} Platform Health Check & System Diagnostic")
    print("=" * 70)

    # 1. Environment & Runtime Diagnostic
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    env_info = {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "python_version": python_ver,
        "project_root": str(PROJECT_ROOT),
        "random_seed": settings.RANDOM_SEED,
    }

    print(f"[*] Application:     {env_info['app_name']} (Env: {env_info['environment']})")
    print(f"[*] Python Runtime:  v{env_info['python_version']}")
    print(f"[*] Project Root:    {env_info['project_root']}")
    print(f"[*] Random Seed:     {env_info['random_seed']}")

    # 2. Database Connectivity Diagnostic
    db_status = check_database_connectivity()
    print(f"\n[*] Database Dialect: {db_status.get('dialect', 'unknown')}")
    print(f"[*] Database Name:    {db_status.get('database', 'unknown')}")
    print(f"[*] Connection State: {'CONNECTED' if db_status.get('connected') else 'DISCONNECTED'}")
    print(f"[*] Ping Latency:     {db_status.get('ping_latency_ms', 0)} ms")

    if not db_status.get("connected"):
        print(f"[-] Database Error:   {db_status.get('error')}")

    # 3. Storage & Directories Diagnostic
    dirs_to_check = [
        ("Raw Data", settings.RAW_DATA_DIR),
        ("Processed Data", settings.PROCESSED_DATA_DIR),
        ("Sample Data", settings.SAMPLE_DATA_DIR),
        ("Quarantine Data", settings.QUARANTINE_DATA_DIR),
        ("Logs Directory", settings.LOGS_DIR),
        ("Schema Directory", settings.SCHEMA_DIR),
    ]

    print("\n[*] Directory Structure Status:")
    dir_status = {}
    for label, dir_path in dirs_to_check:
        exists = dir_path.exists()
        dir_status[label] = exists
        status_symbol = "[OK]" if exists else "[MISSING]"
        print(f"    - {label:<18}: {status_symbol} {dir_path}")

    # 4. Source 1 Customer CSV Check
    csv_exists = settings.CUSTOMERS_CSV_PATH.exists()
    print(f"\n[*] Ingestion Source 1 (CSV): {'[PRESENT]' if csv_exists else '[PENDING SEED]'}")
    if csv_exists:
        print(f"    Location: {settings.CUSTOMERS_CSV_PATH}")

    overall_status = "healthy" if db_status.get("connected") else "degraded"
    summary = {
        "overall_status": overall_status,
        "runtime": env_info,
        "database": db_status,
        "directories": dir_status,
        "source_csv_present": csv_exists
    }

    print("\n" + "=" * 70)
    print(f"  System Health Check Status: {overall_status.upper()}")
    print("=" * 70 + "\n")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{settings.APP_NAME} Platform CLI")
    parser.add_argument("--health", action="store_true", help="Run application health check")
    parser.add_argument("--pipeline", action="store_true", help="Run the DataPulse ELT pipeline")
    parser.add_argument("--api", action="store_true", help="Launch mock REST API server")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit dashboard")
    args = parser.parse_args()

    if args.pipeline:
        from scripts.run_pipeline import main as run_pipe
        run_pipe()
    elif args.api:
        import uvicorn
        print(f"Starting {settings.APP_NAME} REST API on http://{settings.API_HOST}:{settings.API_PORT}...")
        uvicorn.run("app.api.app:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
    elif args.dashboard:
        import subprocess
        print(f"Starting {settings.APP_NAME} Dashboard on port 8501...")
        subprocess.run(["streamlit", "run", "dashboard/app.py"])
    else:
        # Default behavior: run health check
        run_health_check()


if __name__ == "__main__":
    main()

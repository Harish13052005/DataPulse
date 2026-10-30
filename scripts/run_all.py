"""
DataPulse Master Workflow Runner.

Executes the complete project lifecycle sequentially:
1. Deterministic Seed Data Generation
2. Pytest Automated Test Suite Verification (unit + integration)
3. ELT Pipeline Execution & Idempotent Warehouse Loading
4. Analytical Reports Export
5. Performance Benchmarks
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure safe UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def print_banner(text: str) -> None:
    print("\n" + "=" * 70)
    print(f" {text}")
    print("=" * 70)


def run_step(description: str, cmd: list[str]) -> bool:
    print_banner(description)
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"\n[FAILED] {description}")
        return False
    print(f"[PASSED] {description}")
    return True


def main() -> None:
    print("\n" + "#" * 70)
    print("#  DataPulse – Intelligent Data Engineering & Analytics Platform")
    print("#  Complete Assessment Pipeline Verification Suite")
    print("#" * 70)

    # Step 1: Seed Generation
    if not run_step("Step 1: Generating Deterministic Seed Data", [sys.executable, "scripts/generate_seed_data.py"]):
        sys.exit(1)

    # Step 2: Automated Pytest Suite
    if not run_step("Step 2: Executing Pytest Automated Test Suite", [sys.executable, "-m", "pytest"]):
        sys.exit(1)

    # Step 3: Run Pipeline & Export Reports
    if not run_step("Step 3: Running Pipeline & Exporting Reports", [sys.executable, "scripts/run_pipeline.py", "--export-reports"]):
        sys.exit(1)

    # Step 4: Run Performance Benchmarks
    if not run_step("Step 4: Running Performance & Latency Benchmarks", [sys.executable, "scripts/benchmark_performance.py"]):
        sys.exit(1)

    # Step 5: Run Application Health Check
    if not run_step("Step 5: Running Application Health Check", [sys.executable, "main.py", "--health"]):
        sys.exit(1)

    print("\n" + "#" * 70)
    print("#  [SUCCESS] ALL STAGES VERIFIED AND EXECUTED SUCCESSFULLY!")
    print("#" * 70)
    print("\nTo launch the interactive services:")
    print("  1. Interactive Streamlit Dashboard:")
    print("     streamlit run dashboard/app.py")
    print("\n  2. Standalone Mock Orders REST API:")
    print("     uvicorn app.api.mock_app:app --reload --port 8000  # order source")
    print("     python main.py --api  # application API on port 8001")
    print("\n  3. Full Docker Compose Deployment (PostgreSQL + API + Dashboard):")
    print("     docker compose up --build")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

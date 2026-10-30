import sys
from pathlib import Path

# Ensure the project root (two levels up from this file) is in PYTHONPATH for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

"""Allow tests to run from the repository root without setting PYTHONPATH."""
import sys
from pathlib import Path
backend = str(Path(__file__).resolve().parents[1])
if backend not in sys.path: sys.path.insert(0, backend)

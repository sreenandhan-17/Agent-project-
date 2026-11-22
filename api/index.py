"""Vercel entrypoint: serves the FastAPI app as one Python function.

vercel.json rewrites /api/* here; FastAPI still sees the original path (/api/tickets, ...).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]

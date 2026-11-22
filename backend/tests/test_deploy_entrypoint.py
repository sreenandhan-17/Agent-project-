"""Step 6: the Vercel entrypoint and production requirements stay in sync with the app."""

import re
import runpy

from app.config import BACKEND_DIR

ROOT = BACKEND_DIR.parent


def test_vercel_entrypoint_exposes_the_app():
    app = runpy.run_path(str(ROOT / "api" / "index.py"))["app"]
    paths = {r.path for r in app.routes}
    assert {"/api/health", "/api/auth/login", "/api/tickets", "/api/public/tickets"} <= paths


def test_root_requirements_cover_runtime_packages():
    """Vercel installs only the root requirements.txt; keep it aligned with backend/."""
    names = lambda text: {
        re.split(r"[\[=<>~ ]", line.strip())[0].lower()
        for line in text.splitlines() if line.strip() and not line.startswith("#")
    }
    prod = names((ROOT / "requirements.txt").read_text(encoding="utf-8"))
    dev = names((BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8"))
    assert dev - prod == {"uvicorn", "alembic", "pytest", "httpx"}, "runtime dep missing from root"
    assert prod <= dev

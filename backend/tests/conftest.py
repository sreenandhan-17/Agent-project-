import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import BACKEND_DIR, get_settings
from app.db import get_session
from app.main import app


@pytest.fixture(scope="session")
def db_url() -> str:
    settings = get_settings()
    return settings.test_database_url or settings.database_url


@pytest.fixture(scope="session")
def engine(db_url: str) -> Engine:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["url"] = db_url
    command.upgrade(cfg, "head")
    eng = create_engine(db_url, poolclass=NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine: Engine) -> TestClient:
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def _session():
        with test_sessions() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()

from datetime import datetime
from itertools import count

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import BACKEND_DIR, get_settings
from app.db import get_session
from app.main import app
from app.models import Agent, AuditEvent, Customer, Priority, Ticket, TicketStatus
from app.sla.policy import compute_deadlines


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


# --- Rolled-back database access -----------------------------------------------------------
# Everything a test writes (including through the API) is undone at the end, so audit rows,
# which can never be deleted, don't pile up in the test database.


@pytest.fixture
def connection(engine: Engine):
    conn = engine.connect()
    outer = conn.begin()
    yield conn
    outer.rollback()
    conn.close()


def _session_on(conn) -> Session:
    # commit() inside code under test only releases a savepoint.
    return Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def session(connection) -> Session:
    s = _session_on(connection)
    yield s
    s.close()


@pytest.fixture
def api(connection) -> TestClient:
    """TestClient whose requests run inside the test's rolled-back transaction."""

    def _session():
        s = _session_on(connection)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Factories ---------------------------------------------------------------------------

_seq = count(1)


@pytest.fixture
def agent(session: Session) -> Agent:
    n = next(_seq)
    a = Agent(name=f"Test Agent {n}", email=f"agent{n}@test.example", password_hash="x")
    session.add(a)
    session.flush()
    return a


@pytest.fixture
def customer(session: Session) -> Customer:
    n = next(_seq)
    c = Customer(name=f"Test Customer {n}", email=f"customer{n}@test.example")
    session.add(c)
    session.flush()
    return c


@pytest.fixture
def make_ticket(session: Session, customer: Customer):
    def _make(
        created_at: datetime,
        priority: Priority = Priority.MEDIUM,
        status: TicketStatus = TicketStatus.OPEN,
        **fields,
    ) -> Ticket:
        t = Ticket(
            subject="Test ticket",
            customer_id=customer.id,
            priority=priority,
            status=status,
            created_at=created_at,
            **{"paused_minutes": 0, "reopen_count": 0, **fields},
        )
        t.first_response_due_at, t.resolution_due_at = compute_deadlines(t, set())
        session.add(t)
        session.flush()
        return t

    return _make


def audit_actions(session: Session, ticket_id: int) -> list[str]:
    session.flush()
    rows = session.scalars(
        select(AuditEvent.action).where(AuditEvent.ticket_id == ticket_id).order_by(AuditEvent.id)
    )
    return [a.value for a in rows]

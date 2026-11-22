"""INC-0318: audit_events must be append-only, enforced by the database.

Each test runs inside a transaction that is rolled back, so no test rows are left behind
(they could never be deleted otherwise).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditAction, AuditEvent, AuthorType
from app.services.audit import record_event


@pytest.fixture
def session(engine: Engine):
    conn = engine.connect()
    outer = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield s
    s.close()
    outer.rollback()
    conn.close()


@pytest.fixture
def event_id(session: Session) -> int:
    event = record_event(
        session, None, AuthorType.SYSTEM, None, AuditAction.TICKET_CREATED, new={"test": True}
    )
    session.flush()
    return event.id


def _expect_blocked(session: Session, sql: str, **params) -> None:
    with pytest.raises(DBAPIError, match="append-only"):
        with session.begin_nested():
            session.execute(text(sql), params)


def test_update_is_blocked(session: Session, event_id: int):
    _expect_blocked(session, "UPDATE audit_events SET action = 'CLAIMED' WHERE id = :id", id=event_id)


def test_delete_is_blocked(session: Session, event_id: int):
    _expect_blocked(session, "DELETE FROM audit_events WHERE id = :id", id=event_id)


def test_truncate_is_blocked(session: Session, event_id: int):
    _expect_blocked(session, "TRUNCATE audit_events")


def test_row_survives_blocked_changes(session: Session, event_id: int):
    _expect_blocked(session, "DELETE FROM audit_events WHERE id = :id", id=event_id)
    assert session.get(AuditEvent, event_id) is not None


def test_client_supplied_timestamp_is_ignored(session: Session):
    fake = datetime(2000, 1, 1, tzinfo=timezone.utc)
    event = AuditEvent(
        actor_type=AuthorType.SYSTEM, action=AuditAction.TICKET_CREATED, created_at=fake
    )
    session.add(event)
    session.flush()
    session.refresh(event)
    assert event.created_at.year >= 2026

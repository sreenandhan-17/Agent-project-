"""Step 7: auto-close (§3.4). WAITING_ON_CUSTOMER/RESOLVED tickets close after 5 working days
(2700 working minutes) with no customer reply, clock counting from paused_at/resolved_at,
actor = SYSTEM, idempotent.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditAction, AuditEvent, AuthorType, Ticket, TicketStatus
from app.services.tickets import AUTO_CLOSE_WORKING_MINUTES, auto_close_overdue_tickets
from app.sla.working_hours import TZ, add_working_minutes
from tests.conftest import audit_actions, auth_headers

S = TicketStatus
NO_HOLIDAYS: set = set()


def ist(day: int, hour: int, minute: int = 0, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


ANCHOR = ist(23, 10)  # Monday 10:00
AT_THRESHOLD = add_working_minutes(ANCHOR, AUTO_CLOSE_WORKING_MINUTES, NO_HOLIDAYS)
BEFORE_THRESHOLD = add_working_minutes(ANCHOR, AUTO_CLOSE_WORKING_MINUTES - 1, NO_HOLIDAYS)


def event(session, ticket_id: int, action: AuditAction) -> AuditEvent:
    session.flush()
    return session.scalars(
        select(AuditEvent).where(AuditEvent.ticket_id == ticket_id, AuditEvent.action == action)
    ).one()


# --- Waiting-on-customer ---------------------------------------------------------------


def test_waiting_ticket_past_threshold_closes(session, make_ticket):
    ticket = make_ticket(ANCHOR, status=S.WAITING_ON_CUSTOMER, paused_at=ANCHOR)
    closed = auto_close_overdue_tickets(session, now=AT_THRESHOLD, holidays=NO_HOLIDAYS)
    assert [t.id for t in closed] == [ticket.id]
    assert ticket.status is S.CLOSED


def test_waiting_ticket_before_threshold_is_untouched(session, make_ticket):
    ticket = make_ticket(ANCHOR, status=S.WAITING_ON_CUSTOMER, paused_at=ANCHOR)
    closed = auto_close_overdue_tickets(session, now=BEFORE_THRESHOLD, holidays=NO_HOLIDAYS)
    assert closed == []
    assert ticket.status is S.WAITING_ON_CUSTOMER


# --- Resolved ----------------------------------------------------------------------------


def test_resolved_ticket_past_threshold_closes(session, make_ticket):
    ticket = make_ticket(ANCHOR, status=S.RESOLVED, resolved_at=ANCHOR)
    closed = auto_close_overdue_tickets(session, now=AT_THRESHOLD, holidays=NO_HOLIDAYS)
    assert [t.id for t in closed] == [ticket.id]
    assert ticket.status is S.CLOSED


def test_resolved_ticket_before_threshold_is_untouched(session, make_ticket):
    ticket = make_ticket(ANCHOR, status=S.RESOLVED, resolved_at=ANCHOR)
    closed = auto_close_overdue_tickets(session, now=BEFORE_THRESHOLD, holidays=NO_HOLIDAYS)
    assert closed == []
    assert ticket.status is S.RESOLVED


# --- Untouched statuses --------------------------------------------------------------------


@pytest.mark.parametrize("status", [S.NEW, S.OPEN, S.REOPENED, S.CLOSED])
def test_other_statuses_are_never_auto_closed(session, make_ticket, status):
    kwargs = {"resolved_at": ANCHOR} if status is S.CLOSED else {}
    ticket = make_ticket(ANCHOR, status=status, **kwargs)
    closed = auto_close_overdue_tickets(session, now=AT_THRESHOLD, holidays=NO_HOLIDAYS)
    assert ticket.id not in [t.id for t in closed]
    assert ticket.status is status


# --- Idempotency, actor, audit ---------------------------------------------------------------


def test_running_twice_closes_only_once(session, make_ticket):
    ticket = make_ticket(ANCHOR, status=S.WAITING_ON_CUSTOMER, paused_at=ANCHOR)
    first = auto_close_overdue_tickets(session, now=AT_THRESHOLD, holidays=NO_HOLIDAYS)
    second = auto_close_overdue_tickets(
        session, now=AT_THRESHOLD + timedelta(days=1), holidays=NO_HOLIDAYS
    )
    assert len(first) == 1
    assert second == []
    assert audit_actions(session, ticket.id).count("AUTO_CLOSED") == 1
    assert audit_actions(session, ticket.id).count("STATUS_CHANGED") == 1


def test_actor_is_system_for_both_audit_events(session, make_ticket):
    ticket = make_ticket(ANCHOR, status=S.RESOLVED, resolved_at=ANCHOR)
    auto_close_overdue_tickets(session, now=AT_THRESHOLD, holidays=NO_HOLIDAYS)

    status_event = event(session, ticket.id, AuditAction.STATUS_CHANGED)
    auto_closed_event = event(session, ticket.id, AuditAction.AUTO_CLOSED)
    for e in (status_event, auto_closed_event):
        assert e.actor_type is AuthorType.SYSTEM
        assert e.actor_id is None
    assert auto_closed_event.new_value >= AUTO_CLOSE_WORKING_MINUTES


def test_multiple_overdue_tickets_all_close_in_one_run(session, make_ticket):
    a = make_ticket(ANCHOR, status=S.WAITING_ON_CUSTOMER, paused_at=ANCHOR)
    b = make_ticket(ANCHOR, status=S.RESOLVED, resolved_at=ANCHOR)
    c = make_ticket(ANCHOR, status=S.OPEN)  # not a candidate

    closed_ids = {t.id for t in auto_close_overdue_tickets(session, now=AT_THRESHOLD, holidays=NO_HOLIDAYS)}
    assert closed_ids == {a.id, b.id}
    assert c.status is S.OPEN


# --- End-to-end via the cron endpoint (real wall-clock time) --------------------------------


def test_cron_endpoint_closes_a_real_overdue_ticket(api, session, make_ticket):
    old = datetime.now(timezone.utc) - timedelta(days=30)  # robust regardless of when run
    ticket = make_ticket(old, status=S.WAITING_ON_CUSTOMER, paused_at=old)

    headers = {"Authorization": f"Bearer {get_settings().cron_secret}"}
    r = api.get("/api/cron/auto-close", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert ticket.id in body["ticket_ids"]
    assert body["closed"] >= 1

    session.expire_all()
    assert session.get(Ticket, ticket.id).status is S.CLOSED


def test_cron_endpoint_leaves_recent_tickets_alone(api, session, make_ticket):
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    ticket = make_ticket(recent, status=S.WAITING_ON_CUSTOMER, paused_at=recent)

    headers = {"Authorization": f"Bearer {get_settings().cron_secret}"}
    r = api.get("/api/cron/auto-close", headers=headers)
    assert r.status_code == 200
    assert ticket.id not in r.json()["ticket_ids"]
    session.refresh(ticket)
    assert ticket.status is S.WAITING_ON_CUSTOMER

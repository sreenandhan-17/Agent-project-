"""Build step 3: status transitions (Â§5), SLA pause/resume (Â§3.3), priority change (Â§3.6).

Reference week (Nov 2026): Fri 20, Sat 21, Sun 22, Mon 23, Tue 24, Wed 25, Thu 26, Fri 27.
"""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import AuditAction, AuditEvent, AuthorType, Priority, TicketStatus
from app.services.audit import Actor
from app.services.tickets import ALLOWED_TRANSITIONS, InvalidTransition, change_priority, transition
from app.sla.policy import deadlines_for
from app.sla.working_hours import TZ
from tests.conftest import audit_actions

S = TicketStatus
NO_HOLIDAYS: set = set()


def ist(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


@pytest.fixture
def actor(agent) -> Actor:
    return Actor.agent(agent.id)


def move(session, ticket, to, actor, now):
    transition(session, ticket, to, actor, now=now, holidays=NO_HOLIDAYS)


# --- Transition table --------------------------------------------------------------------

ALLOWED = [(f, t) for f, targets in ALLOWED_TRANSITIONS.items() for t in sorted(targets)]
DISALLOWED = [
    (f, t) for f in TicketStatus for t in TicketStatus if t not in ALLOWED_TRANSITIONS[f]
]


def test_table_matches_project_summary():
    assert ALLOWED_TRANSITIONS == {
        S.NEW: {S.OPEN, S.CLOSED},
        S.OPEN: {S.WAITING_ON_CUSTOMER, S.RESOLVED},
        S.WAITING_ON_CUSTOMER: {S.OPEN, S.RESOLVED, S.CLOSED},
        S.RESOLVED: {S.CLOSED, S.REOPENED},
        S.CLOSED: {S.REOPENED},
        S.REOPENED: {S.WAITING_ON_CUSTOMER, S.RESOLVED},
    }


@pytest.mark.parametrize("from_s, to_s", ALLOWED, ids=lambda s: s.value)
def test_allowed_transition_applies_and_is_audited(session, make_ticket, actor, from_s, to_s):
    paused_at = ist(23, 11) if from_s is S.WAITING_ON_CUSTOMER else None
    ticket = make_ticket(ist(23, 10), status=from_s, paused_at=paused_at)
    move(session, ticket, to_s, actor, ist(23, 12))

    assert ticket.status is to_s
    event = session.scalars(
        select(AuditEvent).where(
            AuditEvent.ticket_id == ticket.id, AuditEvent.action == AuditAction.STATUS_CHANGED
        )
    ).one()
    assert (event.old_value, event.new_value) == (from_s.value, to_s.value)
    assert (event.actor_type, event.actor_id) == (AuthorType.AGENT, actor.id)


@pytest.mark.parametrize("from_s, to_s", DISALLOWED, ids=lambda s: s.value)
def test_disallowed_transition_rejected_without_side_effects(
    session, make_ticket, actor, from_s, to_s
):
    ticket = make_ticket(ist(23, 10), status=from_s)
    with pytest.raises(InvalidTransition) as err:
        move(session, ticket, to_s, actor, ist(23, 12))

    assert ticket.status is from_s
    assert audit_actions(session, ticket.id) == []
    assert err.value.allowed == sorted(s.value for s in ALLOWED_TRANSITIONS[from_s])


# --- Side effects of specific statuses ---------------------------------------------------


def test_resolve_and_close_set_timestamps(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10))
    move(session, ticket, S.RESOLVED, actor, ist(23, 15))
    assert ticket.resolved_at == ist(23, 15)
    move(session, ticket, S.CLOSED, actor, ist(24, 10))
    assert ticket.closed_at == ist(24, 10)


def test_reopen_counts_and_clears_resolution(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10))
    move(session, ticket, S.RESOLVED, actor, ist(23, 15))
    move(session, ticket, S.REOPENED, actor, ist(24, 10))
    assert ticket.reopen_count == 1
    assert ticket.resolved_at is None and ticket.closed_at is None


# --- SLA pause / resume (Â§3.3) -----------------------------------------------------------


def test_waiting_pauses_the_clock(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10))
    move(session, ticket, S.WAITING_ON_CUSTOMER, actor, ist(23, 11))
    assert ticket.paused_at == ist(23, 11)
    assert audit_actions(session, ticket.id) == ["STATUS_CHANGED", "SLA_PAUSED"]


def test_resume_shifts_deadlines_by_paused_working_minutes(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10), priority=Priority.MEDIUM)
    move(session, ticket, S.WAITING_ON_CUSTOMER, actor, ist(23, 11))
    move(session, ticket, S.OPEN, actor, ist(23, 13))  # 2 working hours paused

    assert ticket.paused_minutes == 120
    assert ticket.paused_at is None
    expected = deadlines_for(Priority.MEDIUM, ist(23, 10), 120, NO_HOLIDAYS)
    assert (ticket.first_response_due_at, ticket.resolution_due_at) == expected
    assert ticket.first_response_due_at == ist(23, 16, 30)  # 14:30 + 2h
    assert audit_actions(session, ticket.id)[-2:] == ["STATUS_CHANGED", "SLA_RESUMED"]


def test_pause_over_weekend_counts_only_working_minutes(session, make_ticket, actor):
    ticket = make_ticket(ist(20, 10), priority=Priority.LOW)
    before = (ticket.first_response_due_at, ticket.resolution_due_at)
    move(session, ticket, S.WAITING_ON_CUSTOMER, actor, ist(20, 17, 30))
    move(session, ticket, S.OPEN, actor, ist(23, 10, 30))  # Fri 17:30 -> Mon 10:30

    assert ticket.paused_minutes == 120  # 60 Friday + 60 Monday, weekend free
    assert ticket.resolution_due_at > before[1]


def test_pause_entirely_outside_hours_adds_nothing(session, make_ticket, actor):
    ticket = make_ticket(ist(20, 10), priority=Priority.LOW)
    before = (ticket.first_response_due_at, ticket.resolution_due_at)
    move(session, ticket, S.WAITING_ON_CUSTOMER, actor, ist(20, 18, 30))
    move(session, ticket, S.OPEN, actor, ist(23, 9, 30))

    assert ticket.paused_minutes == 0
    assert (ticket.first_response_due_at, ticket.resolution_due_at) == before


def test_repeated_pauses_accumulate(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10))
    move(session, ticket, S.WAITING_ON_CUSTOMER, actor, ist(23, 11))
    move(session, ticket, S.OPEN, actor, ist(23, 12))  # +60
    move(session, ticket, S.WAITING_ON_CUSTOMER, actor, ist(24, 10))
    move(session, ticket, S.OPEN, actor, ist(24, 10, 45))  # +45
    assert ticket.paused_minutes == 105


@pytest.mark.parametrize("to_s", [S.RESOLVED, S.CLOSED])
def test_leaving_waiting_for_resolved_or_closed_ends_the_pause(session, make_ticket, to_s):
    ticket = make_ticket(ist(23, 10))
    move(session, ticket, S.WAITING_ON_CUSTOMER, Actor.system(), ist(23, 11))
    move(session, ticket, to_s, Actor.system(), ist(23, 12))
    assert ticket.paused_at is None
    assert ticket.paused_minutes == 60


def test_system_actor_recorded_without_id(session, make_ticket):
    ticket = make_ticket(ist(23, 10), status=S.WAITING_ON_CUSTOMER, paused_at=ist(23, 11))
    move(session, ticket, S.CLOSED, Actor.system(), ist(30, 10))
    events = session.scalars(select(AuditEvent).where(AuditEvent.ticket_id == ticket.id)).all()
    assert {(e.actor_type, e.actor_id) for e in events} == {(AuthorType.SYSTEM, None)}


# --- Priority change (Â§3.6) --------------------------------------------------------------


def test_priority_change_recomputes_from_created_at_and_can_breach(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10), priority=Priority.LOW)
    assert ticket.first_response_due_at == ist(24, 10)  # LOW: 510 min Mon + 30 min Tue

    changed = change_priority(session, ticket, Priority.URGENT, actor, holidays=NO_HOLIDAYS)

    assert changed
    assert ticket.first_response_due_at == ist(23, 12)
    assert ticket.resolution_due_at == ist(23, 18, 30)
    assert ticket.first_response_due_at < ist(25, 10)  # changed on Wednesday: already breached


def test_priority_change_keeps_paused_minutes(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10), priority=Priority.LOW, paused_minutes=60)
    change_priority(session, ticket, Priority.MEDIUM, actor, holidays=NO_HOLIDAYS)
    assert (ticket.first_response_due_at, ticket.resolution_due_at) == deadlines_for(
        Priority.MEDIUM, ist(23, 10), 60, NO_HOLIDAYS
    )


def test_priority_change_audits_old_and_new_deadlines(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10), priority=Priority.LOW)
    change_priority(session, ticket, Priority.URGENT, actor, holidays=NO_HOLIDAYS)
    session.flush()
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.PRIORITY_CHANGED)
        .where(AuditEvent.ticket_id == ticket.id)
    ).one()
    assert event.old_value["priority"] == "LOW"
    assert event.new_value["priority"] == "URGENT"
    assert event.old_value["first_response_due_at"] != event.new_value["first_response_due_at"]
    assert set(event.new_value) == {
        "priority", "needs_triage", "first_response_due_at", "resolution_due_at"
    }


def test_same_priority_is_a_no_op(session, make_ticket, actor):
    ticket = make_ticket(ist(23, 10), priority=Priority.LOW)
    assert change_priority(session, ticket, Priority.LOW, actor, holidays=NO_HOLIDAYS) is False
    assert audit_actions(session, ticket.id) == []

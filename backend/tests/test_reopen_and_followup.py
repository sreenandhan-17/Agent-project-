"""Step 7: reopen within 7 calendar days (§3.5), follow-up tickets after the window, and
blocking agent replies on CLOSED tickets (note 17).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import AuditAction, AuditEvent, Priority, Ticket, TicketStatus
from app.services.audit import Actor
from app.services.tickets import (
    REOPEN_WINDOW_DAYS,
    ReopenWindowExpired,
    TicketClosed,
    add_customer_reply,
    add_reply,
    create_follow_up,
    reopen,
)
from app.sla.policy import deadlines_for
from app.sla.working_hours import TZ
from tests.conftest import audit_actions, auth_headers

S = TicketStatus
NO_HOLIDAYS: set = set()


def ist(day: int, hour: int, minute: int = 0, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


RESOLVED_AT = ist(23, 15)  # Monday 15:00


@pytest.fixture
def resolved_ticket(make_ticket, agent):
    return make_ticket(
        ist(16, 10), status=S.RESOLVED, resolved_at=RESOLVED_AT, priority=Priority.MEDIUM,
        assignee_id=agent.id,
    )


@pytest.fixture
def closed_ticket(make_ticket, agent):
    """Never resolved (e.g. auto-closed while waiting): §3.5 says anchor on closed_at."""
    return make_ticket(
        ist(16, 10), status=S.CLOSED, closed_at=RESOLVED_AT, priority=Priority.MEDIUM,
        assignee_id=agent.id,
    )


def event(session, ticket_id: int, action: AuditAction) -> AuditEvent:
    session.flush()
    return session.scalars(
        select(AuditEvent).where(AuditEvent.ticket_id == ticket_id, AuditEvent.action == action)
    ).one()


# --- reopen(): window ----------------------------------------------------------------------


def test_reopen_within_window_succeeds_and_sets_fresh_deadline(session, agent, resolved_ticket):
    now = RESOLVED_AT + timedelta(days=3)
    before = resolved_ticket.resolution_due_at
    reopen(session, resolved_ticket, Actor.agent(agent.id), now=now, holidays=NO_HOLIDAYS)

    assert resolved_ticket.status is S.REOPENED
    assert resolved_ticket.reopen_count == 1
    assert resolved_ticket.resolved_at is None
    _, expected_resolution = deadlines_for(resolved_ticket.priority, now, 0, NO_HOLIDAYS)
    assert resolved_ticket.resolution_due_at == expected_resolution
    assert resolved_ticket.resolution_due_at != before


def test_reopen_leaves_first_response_fields_untouched(session, agent, resolved_ticket):
    first_response_at = resolved_ticket.first_response_at
    first_response_due = resolved_ticket.first_response_due_at
    reopen(
        session, resolved_ticket, Actor.agent(agent.id),
        now=RESOLVED_AT + timedelta(hours=1), holidays=NO_HOLIDAYS,
    )
    assert resolved_ticket.first_response_at == first_response_at
    assert resolved_ticket.first_response_due_at == first_response_due


def test_reopen_at_exactly_seven_days_succeeds(session, agent, resolved_ticket):
    now = RESOLVED_AT + timedelta(days=REOPEN_WINDOW_DAYS)
    reopen(session, resolved_ticket, Actor.agent(agent.id), now=now, holidays=NO_HOLIDAYS)
    assert resolved_ticket.status is S.REOPENED


def test_reopen_one_second_past_seven_days_rejected(session, agent, resolved_ticket):
    now = RESOLVED_AT + timedelta(days=REOPEN_WINDOW_DAYS, seconds=1)
    with pytest.raises(ReopenWindowExpired) as err:
        reopen(session, resolved_ticket, Actor.agent(agent.id), now=now, holidays=NO_HOLIDAYS)
    assert resolved_ticket.status is S.RESOLVED  # unchanged: all-or-nothing
    assert err.value.anchor_field == "resolved_at"
    assert audit_actions(session, resolved_ticket.id) == []


def test_reopen_measured_from_closed_at_when_never_resolved(session, agent, closed_ticket):
    now = RESOLVED_AT + timedelta(days=REOPEN_WINDOW_DAYS, seconds=1)
    with pytest.raises(ReopenWindowExpired) as err:
        reopen(session, closed_ticket, Actor.agent(agent.id), now=now, holidays=NO_HOLIDAYS)
    assert err.value.anchor_field == "closed_at"


def test_reopen_from_closed_within_window_succeeds(session, agent, closed_ticket):
    now = RESOLVED_AT + timedelta(days=2)
    reopen(session, closed_ticket, Actor.agent(agent.id), now=now, holidays=NO_HOLIDAYS)
    assert closed_ticket.status is S.REOPENED
    assert closed_ticket.closed_at is None


def test_reopen_audits_old_and_new_resolution_deadline(session, agent, resolved_ticket):
    reopen(
        session, resolved_ticket, Actor.agent(agent.id),
        now=RESOLVED_AT + timedelta(hours=2), holidays=NO_HOLIDAYS,
    )
    e = event(session, resolved_ticket.id, AuditAction.REOPENED)
    assert e.field == "resolution_due_at"
    assert e.old_value != e.new_value
    assert (e.actor_type, e.actor_id) == (Actor.agent(agent.id).type, agent.id)


def test_reopen_twice_increments_count(session, agent, resolved_ticket):
    reopen(
        session, resolved_ticket, Actor.agent(agent.id),
        now=RESOLVED_AT + timedelta(hours=1), holidays=NO_HOLIDAYS,
    )
    # Move it back to resolved to reopen a second time.
    from app.services.tickets import transition

    transition(
        session, resolved_ticket, S.RESOLVED, Actor.agent(agent.id),
        now=RESOLVED_AT + timedelta(hours=2), holidays=NO_HOLIDAYS,
    )
    reopen(
        session, resolved_ticket, Actor.agent(agent.id),
        now=RESOLVED_AT + timedelta(hours=3), holidays=NO_HOLIDAYS,
    )
    assert resolved_ticket.reopen_count == 2


# --- POST /api/tickets/{id}/reopen ---------------------------------------------------------


def test_reopen_endpoint_succeeds_for_assignee(api, session, agent, resolved_ticket):
    headers = auth_headers(agent)
    r = api.post(f"/api/tickets/{resolved_ticket.id}/reopen", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "REOPENED"


def test_reopen_endpoint_403_for_non_assignee(api, session, make_agent, resolved_ticket):
    bystander = make_agent()
    r = api.post(f"/api/tickets/{resolved_ticket.id}/reopen", headers=auth_headers(bystander))
    assert r.status_code == 403
    session.refresh(resolved_ticket)
    assert resolved_ticket.status is S.RESOLVED


def test_reopen_endpoint_409_past_window(api, session, agent, make_ticket):
    # Over HTTP there's no way to pass a fake "now": use a resolved_at far enough in the real
    # past (30 real days) so this holds regardless of when the suite actually runs.
    old = datetime.now(timezone.utc) - timedelta(days=30)
    ticket = make_ticket(
        old, status=S.RESOLVED, resolved_at=old, assignee_id=agent.id,
    )
    r = api.post(f"/api/tickets/{ticket.id}/reopen", headers=auth_headers(agent))
    assert r.status_code == 409
    assert "7 days" in r.json()["detail"]


def test_patch_status_to_reopened_also_enforces_window(api, session, agent, make_ticket):
    """PATCH /status and POST /reopen share transition(): can't diverge."""
    old = datetime.now(timezone.utc) - timedelta(days=30)
    ticket = make_ticket(old, status=S.CLOSED, closed_at=old, assignee_id=agent.id)
    r = api.patch(
        f"/api/tickets/{ticket.id}/status", json={"status": "REOPENED"}, headers=auth_headers(agent)
    )
    assert r.status_code == 409


# --- create_follow_up() ---------------------------------------------------------------------


def test_create_follow_up_links_both_ways_and_audits(session, resolved_ticket):
    new_ticket, message = create_follow_up(
        session, resolved_ticket, "Still broken, please help", now=ist(30, 10), holidays=NO_HOLIDAYS
    )
    assert new_ticket.parent_ticket_id == resolved_ticket.id
    assert new_ticket.status is S.NEW
    assert new_ticket.priority == resolved_ticket.priority
    assert new_ticket.needs_triage is True
    assert new_ticket.customer_id == resolved_ticket.customer_id
    assert message.ticket_id == new_ticket.id
    assert message.body == "Still broken, please help"

    assert event(session, resolved_ticket.id, AuditAction.FOLLOW_UP_CREATED).new_value == new_ticket.id
    created = event(session, new_ticket.id, AuditAction.TICKET_CREATED)
    assert created.new_value["parent_ticket_id"] == resolved_ticket.id

    # The old ticket is untouched: still resolved, no message added to it.
    assert resolved_ticket.status is S.RESOLVED
    assert not any(m.ticket_id == resolved_ticket.id and m.body == message.body
                   for m in resolved_ticket.messages)


# --- add_customer_reply(): wired through reopen / follow-up ---------------------------------


def test_customer_reply_within_window_reopens_same_ticket(session, resolved_ticket):
    now = RESOLVED_AT + timedelta(days=1)
    resulting_ticket, message = add_customer_reply(
        session, resolved_ticket, "Any update?", now=now
    )
    assert resulting_ticket.id == resolved_ticket.id
    assert resulting_ticket.status is S.REOPENED
    assert message.ticket_id == resolved_ticket.id


def test_customer_reply_past_window_creates_follow_up(session, resolved_ticket):
    now = RESOLVED_AT + timedelta(days=REOPEN_WINDOW_DAYS, hours=1)
    resulting_ticket, message = add_customer_reply(
        session, resolved_ticket, "Still an issue weeks later", now=now
    )
    assert resulting_ticket.id != resolved_ticket.id
    assert resulting_ticket.parent_ticket_id == resolved_ticket.id
    assert message.ticket_id == resulting_ticket.id
    # The original ticket keeps its resolved status; the new message is NOT on it.
    session.refresh(resolved_ticket, ["messages"])
    assert resolved_ticket.status is S.RESOLVED
    assert "Still an issue weeks later" not in [m.body for m in resolved_ticket.messages]


def test_customer_reply_on_waiting_ticket_still_just_resumes(session, make_ticket):
    """Regression: the RESOLVED/CLOSED branch must not swallow the ordinary waiting case."""
    ticket = make_ticket(ist(23, 10), status=S.WAITING_ON_CUSTOMER, paused_at=ist(23, 11))
    resulting_ticket, message = add_customer_reply(session, ticket, "I'm back", now=ist(23, 13))
    assert resulting_ticket.id == ticket.id
    assert ticket.status is S.OPEN
    assert message.ticket_id == ticket.id


# --- Public API: follow-up redirect -----------------------------------------------------


def test_public_reply_past_window_returns_new_token(api, session, make_ticket):
    old = datetime.now(timezone.utc) - timedelta(days=30)
    ticket = make_ticket(old, status=S.RESOLVED, resolved_at=old)
    r = api.post(f"/api/public/tickets/{ticket.public_token}/replies", json={"body": "Hello again"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"] != ticket.public_token
    assert body["ticket"]["messages"][-1]["body"] == "Hello again"

    session.expire_all()
    new_ticket = session.scalars(
        select(Ticket).where(Ticket.public_token == body["token"])
    ).one()
    assert new_ticket.parent_ticket_id == ticket.id


def test_public_reply_within_window_keeps_same_token(api, make_ticket):
    recent = datetime.now(timezone.utc) - timedelta(days=2)
    ticket = make_ticket(recent, status=S.RESOLVED, resolved_at=recent)
    r = api.post(f"/api/public/tickets/{ticket.public_token}/replies", json={"body": "Thanks!"})
    assert r.status_code == 201, r.text
    assert r.json()["token"] == ticket.public_token
    assert r.json()["ticket"]["status"] == "REOPENED"


# --- note 17: block agent replies on CLOSED, allow on RESOLVED, notes always allowed --------


def test_agent_reply_blocked_on_closed_ticket(session, agent, make_ticket):
    ticket = make_ticket(ist(16, 10), status=S.CLOSED, closed_at=ist(16, 11), assignee_id=agent.id)
    with pytest.raises(TicketClosed):
        add_reply(session, ticket, agent, "Reopening context")


def test_agent_reply_still_allowed_on_resolved_ticket(session, agent, resolved_ticket):
    message = add_reply(session, resolved_ticket, agent, "One more thing")
    assert message.body == "One more thing"


def test_agent_reply_endpoint_409_on_closed(api, session, agent, make_ticket):
    ticket = make_ticket(ist(16, 10), status=S.CLOSED, closed_at=ist(16, 11), assignee_id=agent.id)
    r = api.post(
        f"/api/tickets/{ticket.id}/replies", json={"body": "hi"}, headers=auth_headers(agent)
    )
    assert r.status_code == 409
    assert "closed" in r.json()["detail"].lower()


def test_internal_note_still_allowed_on_closed_ticket(api, agent, make_ticket):
    ticket = make_ticket(ist(16, 10), status=S.CLOSED, closed_at=ist(16, 11), assignee_id=agent.id)
    r = api.post(
        f"/api/tickets/{ticket.id}/notes", json={"body": "internal only"}, headers=auth_headers(agent)
    )
    assert r.status_code == 201


# --- Linking shown in the agent UI -----------------------------------------------------------


def test_detail_shows_parent_and_follow_up_links(api, session, agent, resolved_ticket):
    new_ticket, _ = create_follow_up(
        session, resolved_ticket, "weeks later", now=ist(30, 10), holidays=NO_HOLIDAYS
    )
    session.commit()
    headers = auth_headers(agent)

    old_detail = api.get(f"/api/tickets/{resolved_ticket.id}", headers=headers).json()
    assert old_detail["follow_up_ticket_number"] == new_ticket.number
    assert old_detail["parent_ticket_number"] is None

    new_detail = api.get(f"/api/tickets/{new_ticket.id}", headers=headers).json()
    assert new_detail["parent_ticket_number"] == resolved_ticket.number
    assert new_detail["follow_up_ticket_number"] is None

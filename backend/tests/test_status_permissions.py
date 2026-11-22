"""Issue 10 decision (§4/§5): who may change status and priority.

PATCH /status: assignee or ADMIN; any agent may close a NEW unassigned ticket (spam/duplicate).
PATCH /priority: any active agent, audited.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import AgentRole, AuditAction, AuditEvent, Ticket, TicketStatus
from tests.conftest import audit_actions, auth_headers

S = TicketStatus
YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)


@pytest.fixture
def owner(make_agent):
    return make_agent()


@pytest.fixture
def bystander(make_agent):
    return make_agent()


@pytest.fixture
def admin(make_agent):
    return make_agent(role=AgentRole.ADMIN)


@pytest.fixture
def owned(make_ticket, owner):
    return make_ticket(YESTERDAY, status=S.OPEN, assignee_id=owner.id)


@pytest.fixture
def unassigned_new(make_ticket):
    return make_ticket(YESTERDAY, status=S.NEW)


def patch_status(api, ticket, agent, to):
    return api.patch(
        f"/api/tickets/{ticket.id}/status", json={"status": to}, headers=auth_headers(agent)
    )


def current_status(session, ticket) -> TicketStatus:
    session.expire_all()
    return session.get(Ticket, ticket.id).status


# --- PATCH /status: allowed --------------------------------------------------------------


def test_assignee_can_change_status(api, session, owner, owned):
    assert patch_status(api, owned, owner, "RESOLVED").status_code == 200
    assert current_status(session, owned) is S.RESOLVED


def test_admin_can_change_status_of_someone_elses_ticket(api, session, admin, owned):
    assert patch_status(api, owned, admin, "WAITING_ON_CUSTOMER").status_code == 200
    events = session.scalars(
        select(AuditEvent).where(
            AuditEvent.ticket_id == owned.id, AuditEvent.action == AuditAction.STATUS_CHANGED
        )
    ).all()
    assert [e.actor_id for e in events] == [admin.id]


def test_any_agent_can_close_new_unassigned_ticket_as_spam(api, session, bystander, unassigned_new):
    r = patch_status(api, unassigned_new, bystander, "CLOSED")
    assert r.status_code == 200, r.text
    assert current_status(session, unassigned_new) is S.CLOSED
    assert audit_actions(session, unassigned_new.id) == ["STATUS_CHANGED"]


# --- PATCH /status: forbidden ------------------------------------------------------------


def test_non_assignee_gets_403_and_nothing_changes(api, session, bystander, owned):
    r = patch_status(api, owned, bystander, "RESOLVED")
    assert r.status_code == 403
    assert current_status(session, owned) is S.OPEN
    assert audit_actions(session, owned.id) == []


def test_unassigned_non_new_ticket_needs_admin(api, session, bystander, make_ticket):
    ticket = make_ticket(YESTERDAY, status=S.OPEN)  # e.g. assignee left; nobody owns it
    assert patch_status(api, ticket, bystander, "RESOLVED").status_code == 403


def test_spam_exception_only_allows_closing(api, bystander, unassigned_new):
    """NEW -> OPEN must go through the claim, not PATCH /status."""
    assert patch_status(api, unassigned_new, bystander, "OPEN").status_code == 403


def test_spam_exception_does_not_cover_assigned_new_tickets(api, bystander, make_ticket, owner):
    ticket = make_ticket(YESTERDAY, status=S.NEW, assignee_id=owner.id)
    assert patch_status(api, ticket, bystander, "CLOSED").status_code == 403


def test_permission_is_checked_before_transition_validity(api, bystander, owned):
    """A non-assignee learns nothing about the ticket's state: 403, not 422."""
    assert patch_status(api, owned, bystander, "NEW").status_code == 403


def test_assignee_invalid_transition_still_422(api, owner, owned):
    assert patch_status(api, owned, owner, "NEW").status_code == 422


# --- PATCH /priority: any active agent ---------------------------------------------------


def test_any_agent_can_change_priority_and_it_is_audited(api, session, bystander, owned):
    r = api.patch(
        f"/api/tickets/{owned.id}/priority", json={"priority": "URGENT"},
        headers=auth_headers(bystander),
    )
    assert r.status_code == 200, r.text
    assert r.json()["priority"] == "URGENT"
    event = session.scalars(
        select(AuditEvent).where(
            AuditEvent.ticket_id == owned.id, AuditEvent.action == AuditAction.PRIORITY_CHANGED
        )
    ).one()
    assert event.actor_id == bystander.id
    assert event.old_value["priority"] == "MEDIUM" and event.new_value["priority"] == "URGENT"


def test_any_agent_can_triage_unassigned_ticket(api, bystander, unassigned_new):
    r = api.patch(
        f"/api/tickets/{unassigned_new.id}/priority", json={"priority": "LOW"},
        headers=auth_headers(bystander),
    )
    assert r.status_code == 200


def test_inactive_agent_cannot_change_priority(api, session, bystander, owned):
    headers = auth_headers(bystander)
    bystander.is_active = False
    session.flush()
    r = api.patch(f"/api/tickets/{owned.id}/priority", json={"priority": "LOW"}, headers=headers)
    assert r.status_code == 401

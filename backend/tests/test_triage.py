"""Issue 15 decision (§3.1): customer tickets start MEDIUM + needs_triage, with an impact hint.

Any agent's PATCH /priority is the triage decision and clears needs_triage (audited).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    AuditAction,
    AuditEvent,
    CustomerImpact,
    Priority,
    Ticket,
    TicketStatus,
)
from tests.conftest import audit_actions, auth_headers

FORM = {
    "name": "Neha Gupta",
    "email": "neha@triage.example",
    "subject": "POS terminals down",
    "body": "None of our stores can bill.",
    "impact": "CANNOT_WORK",
}


def submit(api, **overrides):
    return api.post("/api/public/tickets", json={**FORM, **overrides})


def ticket_for(session, response) -> Ticket:
    session.expire_all()
    token = response.json()["token"]
    return session.scalars(select(Ticket).where(Ticket.public_token == token)).one()


def set_priority(api, ticket, agent, priority):
    return api.patch(
        f"/api/tickets/{ticket.id}/priority", json={"priority": priority},
        headers=auth_headers(agent),
    )


def audit_event(session, ticket, action) -> AuditEvent:
    session.expire_all()
    return session.scalars(
        select(AuditEvent).where(AuditEvent.ticket_id == ticket.id, AuditEvent.action == action)
    ).one()


@pytest.fixture
def flagged(api, session):
    r = submit(api)
    assert r.status_code == 201, r.text
    return ticket_for(session, r)


# --- Intake ------------------------------------------------------------------------------


def test_customer_ticket_starts_medium_and_needs_triage(session, flagged):
    assert flagged.priority is Priority.MEDIUM
    assert flagged.needs_triage is True
    assert flagged.customer_impact is CustomerImpact.CANNOT_WORK
    created = audit_event(session, flagged, AuditAction.TICKET_CREATED)
    assert created.new_value["needs_triage"] is True
    assert created.new_value["customer_impact"] == "CANNOT_WORK"


@pytest.mark.parametrize("impact", ["CANNOT_WORK", "PARTIAL", "QUESTION"])
def test_every_impact_value_accepted(api, session, impact):
    r = submit(api, email=f"{impact.lower()}@triage.example", impact=impact)
    assert r.status_code == 201
    assert ticket_for(session, r).customer_impact is CustomerImpact(impact)


def test_impact_is_required_on_the_public_form(api):
    form = {k: v for k, v in FORM.items() if k != "impact"}
    assert api.post("/api/public/tickets", json=form).status_code == 422


def test_unknown_impact_rejected(api):
    assert submit(api, impact="ON_FIRE").status_code == 422


def test_customer_cannot_choose_priority(api, session):
    r = submit(api, email="sneaky@triage.example", priority="URGENT")
    assert r.status_code == 201
    assert ticket_for(session, r).priority is Priority.MEDIUM


def test_triage_fields_are_not_shown_to_the_customer(api, flagged):
    text = api.get(f"/api/public/tickets/{flagged.public_token}").text
    for internal in ("needs_triage", "customer_impact", "CANNOT_WORK", "MEDIUM"):
        assert internal not in text


def test_agent_created_tickets_do_not_need_triage(make_ticket):
    ticket = make_ticket(datetime.now(timezone.utc) - timedelta(hours=1))
    assert ticket.needs_triage is False
    assert ticket.customer_impact is None


# --- Triage via PATCH /priority ----------------------------------------------------------


def test_new_priority_clears_flag_and_is_audited(api, session, agent, flagged):
    r = set_priority(api, flagged, agent, "URGENT")
    assert r.status_code == 200, r.text
    assert r.json()["needs_triage"] is False
    assert r.json()["priority"] == "URGENT"

    event = audit_event(session, flagged, AuditAction.PRIORITY_CHANGED)
    assert event.actor_id == agent.id
    assert (event.old_value["needs_triage"], event.new_value["needs_triage"]) == (True, False)
    assert (event.old_value["priority"], event.new_value["priority"]) == ("MEDIUM", "URGENT")


def test_confirming_current_priority_clears_flag_as_triaged(api, session, agent, flagged):
    before = (flagged.first_response_due_at, flagged.resolution_due_at)
    r = set_priority(api, flagged, agent, "MEDIUM")
    assert r.status_code == 200
    assert r.json()["needs_triage"] is False

    event = audit_event(session, flagged, AuditAction.TRIAGED)
    assert event.field == "needs_triage"
    assert (event.old_value["needs_triage"], event.new_value["needs_triage"]) == (True, False)
    assert event.new_value["priority"] == "MEDIUM"

    session.expire_all()
    t = session.get(Ticket, flagged.id)
    assert (t.first_response_due_at, t.resolution_due_at) == before  # deadlines untouched
    assert "PRIORITY_CHANGED" not in audit_actions(session, flagged.id)


def test_confirming_again_is_a_no_op(api, session, agent, flagged):
    set_priority(api, flagged, agent, "MEDIUM")
    assert set_priority(api, flagged, agent, "MEDIUM").status_code == 200
    assert audit_actions(session, flagged.id).count("TRIAGED") == 1


def test_any_agent_can_triage_without_claiming(api, session, make_agent, flagged):
    bystander = make_agent()
    assert set_priority(api, flagged, bystander, "LOW").status_code == 200
    session.expire_all()
    t = session.get(Ticket, flagged.id)
    assert t.needs_triage is False and t.assignee_id is None and t.status is TicketStatus.NEW


# --- List --------------------------------------------------------------------------------


def test_list_returns_triage_fields(api, agent, flagged):
    r = api.get("/api/tickets", headers=auth_headers(agent))
    assert r.status_code == 200
    row = next(t for t in r.json() if t["id"] == flagged.id)
    assert row["needs_triage"] is True
    assert row["customer_impact"] == "CANNOT_WORK"


def test_list_can_filter_needs_triage(api, agent, make_ticket, flagged):
    other = make_ticket(datetime.now(timezone.utc) - timedelta(hours=2))
    ids = {t["id"] for t in api.get(
        "/api/tickets", params={"needs_triage": "true"}, headers=auth_headers(agent)
    ).json()}
    assert flagged.id in ids and other.id not in ids

    set_priority(api, flagged, agent, "MEDIUM")
    ids = {t["id"] for t in api.get(
        "/api/tickets", params={"needs_triage": "true"}, headers=auth_headers(agent)
    ).json()}
    assert flagged.id not in ids


def test_list_requires_auth(api):
    assert api.get("/api/tickets").status_code == 401

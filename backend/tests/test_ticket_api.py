"""PATCH /api/tickets/{id}/status and /priority. Runs inside the test's rolled-back transaction."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Priority, TicketStatus
from tests.conftest import audit_actions, auth_headers


@pytest.fixture
def headers(agent) -> dict:
    return auth_headers(agent)


@pytest.fixture
def ticket(make_ticket):
    return make_ticket(datetime.now(timezone.utc) - timedelta(days=1), priority=Priority.LOW)


def test_status_change(api, session, ticket, headers):
    r = api.patch(f"/api/tickets/{ticket.id}/status", json={"status": "RESOLVED"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "RESOLVED"
    assert r.json()["resolved_at"] is not None
    assert audit_actions(session, ticket.id) == ["STATUS_CHANGED"]


def test_invalid_transition_returns_422_with_allowed_list(api, session, ticket, headers):
    r = api.patch(f"/api/tickets/{ticket.id}/status", json={"status": "NEW"}, headers=headers)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["from"] == "OPEN"
    assert detail["allowed"] == ["RESOLVED", "WAITING_ON_CUSTOMER"]
    assert audit_actions(session, ticket.id) == []


def test_unknown_status_value_is_rejected(api, ticket, headers):
    r = api.patch(f"/api/tickets/{ticket.id}/status", json={"status": "DONE"}, headers=headers)
    assert r.status_code == 422


def test_waiting_then_open_via_api(api, ticket, headers):
    url = f"/api/tickets/{ticket.id}/status"
    assert api.patch(url, json={"status": "WAITING_ON_CUSTOMER"}, headers=headers).json()[
        "paused_at"
    ]
    r = api.patch(url, json={"status": "OPEN"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["paused_at"] is None


def test_priority_change(api, session, ticket, headers):
    before = ticket.first_response_due_at
    r = api.patch(f"/api/tickets/{ticket.id}/priority", json={"priority": "URGENT"}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["priority"] == "URGENT"
    assert datetime.fromisoformat(body["first_response_due_at"]) < before
    assert audit_actions(session, ticket.id) == ["PRIORITY_CHANGED"]


def test_unknown_ticket_is_404(api, headers):
    r = api.patch("/api/tickets/999999/status", json={"status": "OPEN"}, headers=headers)
    assert r.status_code == 404


@pytest.mark.parametrize(
    "hdrs", [{}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic abc"}]
)
def test_requires_valid_token(api, session, ticket, hdrs):
    r = api.patch(f"/api/tickets/{ticket.id}/status", json={"status": "RESOLVED"}, headers=hdrs)
    assert r.status_code == 401
    session.refresh(ticket)
    assert ticket.status is TicketStatus.OPEN

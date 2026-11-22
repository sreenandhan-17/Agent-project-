"""INC-0304: internal notes must never reach a customer.

The sentinel is written into an internal note, then every customer-facing output is collected
and searched for it. A route-inventory test makes sure new /api/public routes get covered here.
"""

import json

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.main import app
from app.models import Message, Ticket, Visibility
from app.serializers.customer import CustomerTicketView, serialize_for_customer
from app.services.email import render_customer_email
from tests.conftest import auth_headers

SENTINEL = "SECRET-NOTE-7f3a"

# Every /api/public route, and the test below that exercises it.
COVERED_PUBLIC_ROUTES = {
    ("POST", "/api/public/tickets"),
    ("GET", "/api/public/tickets/{token}"),
    ("POST", "/api/public/tickets/{token}/replies"),
}


def submit(api, email="leak@test.example"):
    r = api.post(
        "/api/public/tickets",
        json={"name": "Leak Tester", "email": email, "subject": "Printer on fire", "body": "Help"},
    )
    assert r.status_code == 201, r.text
    return r


@pytest.fixture
def scenario(api, session, agent):
    """A customer ticket with an internal note (sentinel), a public reply and a customer reply.

    Returns (ticket, {output name: text the customer could see}).
    """
    outputs: dict[str, str] = {}
    hdrs = auth_headers(agent)

    created = submit(api)
    token = created.json()["token"]
    ticket = session.scalars(select(Ticket).where(Ticket.public_token == token)).one()

    assert api.post(f"/api/tickets/{ticket.id}/claim", headers=hdrs).status_code == 200
    r = api.post(
        f"/api/tickets/{ticket.id}/notes",
        json={"body": f"{SENTINEL}: customer owes us money, be careful"},
        headers=hdrs,
    )
    assert r.status_code == 201
    r = api.post(
        f"/api/tickets/{ticket.id}/replies", json={"body": "We are on it."}, headers=hdrs
    )
    assert r.status_code == 201
    reply_id = r.json()["id"]
    api.patch(
        f"/api/tickets/{ticket.id}/status", json={"status": "WAITING_ON_CUSTOMER"}, headers=hdrs
    )

    # --- every customer-facing output ---
    outputs["POST /api/public/tickets"] = submit(api, "second@test.example").text
    outputs["GET /api/public/tickets/{token}"] = api.get(f"/api/public/tickets/{token}").text
    outputs["POST /api/public/tickets/{token}/replies"] = api.post(
        f"/api/public/tickets/{token}/replies", json={"body": "Still broken"}
    ).text
    outputs["GET /api/tickets/{id}/export"] = api.get(
        f"/api/tickets/{ticket.id}/export", headers=hdrs
    ).text

    session.expire_all()
    ticket = session.get(Ticket, ticket.id)
    email = render_customer_email(ticket, session.get(Message, reply_id))
    outputs["email"] = f"{email.to}\n{email.subject}\n{email.body}"
    return ticket, outputs


def test_sentinel_is_really_in_the_database(session, scenario):
    """Guard against a vacuous pass: the note exists and is INTERNAL."""
    ticket, _ = scenario
    notes = [m for m in ticket.messages if SENTINEL in m.body]
    assert len(notes) == 1 and notes[0].visibility is Visibility.INTERNAL


def test_no_customer_facing_output_contains_internal_note(scenario):
    _, outputs = scenario
    assert set(outputs) >= {f"{m} {p}" for m, p in COVERED_PUBLIC_ROUTES}
    for name, text in outputs.items():
        assert text, f"{name} returned nothing"
        assert SENTINEL not in text, f"internal note leaked via {name}"


def test_public_content_does_show_up(scenario):
    """Positive control: the same outputs do carry the public conversation."""
    _, outputs = scenario
    for name in ("GET /api/public/tickets/{token}", "GET /api/tickets/{id}/export", "email"):
        assert "We are on it." in outputs[name], name


def test_customer_reply_resumed_the_sla(scenario):
    ticket, _ = scenario
    assert ticket.status.value == "OPEN"
    assert ticket.paused_at is None


def test_email_refuses_internal_messages(session, scenario):
    ticket, _ = scenario
    internal = next(m for m in ticket.messages if m.visibility is Visibility.INTERNAL)
    with pytest.raises(ValueError):
        render_customer_email(ticket, internal)


# --- Allow-list ----------------------------------------------------------------------------


def test_customer_view_is_exactly_the_allow_list(scenario):
    ticket, _ = scenario
    view = serialize_for_customer(ticket, ticket.messages).model_dump(mode="json")
    assert set(view) == {"number", "subject", "status", "created_at", "messages"}
    for m in view["messages"]:
        assert set(m) == {"id", "author", "author_name", "body", "created_at"}

    blob = json.dumps(view).lower()
    for internal in ("assignee", "paused", "priority", "audit", "visibility", "internal",
                     "public_token", "due_at", "agent"):
        assert internal not in blob, internal


def test_agent_names_are_not_shown_to_customers(session, agent, scenario):
    _, outputs = scenario
    for name, text in outputs.items():
        assert agent.name not in text, name


def test_unknown_token_is_404(api):
    assert api.get("/api/public/tickets/not-a-token").status_code == 404
    r = api.post("/api/public/tickets/not-a-token/replies", json={"body": "hi"})
    assert r.status_code == 404


def test_export_requires_agent_auth(api, scenario):
    ticket, _ = scenario
    assert api.get(f"/api/tickets/{ticket.id}/export").status_code == 401


# --- Route inventory -----------------------------------------------------------------------


def _public_routes() -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/public")
        for method in route.methods
    }


def test_every_public_route_is_leak_tested():
    uncovered = _public_routes() - COVERED_PUBLIC_ROUTES
    assert not uncovered, (
        f"new customer-facing route(s) {uncovered}: add them to the leak test "
        "and COVERED_PUBLIC_ROUTES"
    )
    assert COVERED_PUBLIC_ROUTES <= _public_routes(), "stale entry in COVERED_PUBLIC_ROUTES"


def test_public_routes_only_return_customer_views():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/public"):
            model = route.response_model
            fields = getattr(model, "model_fields", {})
            assert model is CustomerTicketView or (
                set(fields) == {"token", "ticket"}
                and fields["ticket"].annotation is CustomerTicketView
            ), route.path

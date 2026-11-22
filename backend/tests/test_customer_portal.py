"""Issue 18 (customer portal backend) + issue 14 honeypot."""

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Customer, Message, Ticket
from app.services.email import customer_ticket_url, render_customer_email
from tests.conftest import auth_headers

FORM = {
    "name": "Rohan Das",
    "email": "rohan@portal.example",
    "company": "Nimbus Education",
    "subject": "Timetable export fails",
    "body": "The PDF export spins forever.",
    "impact": "PARTIAL",
}


def count(session, model, **where) -> int:
    session.expire_all()
    stmt = select(func.count()).select_from(model)
    for col, value in where.items():
        stmt = stmt.where(getattr(model, col) == value)
    return session.scalar(stmt)


# --- Honeypot ----------------------------------------------------------------------------


def test_filled_honeypot_returns_200_and_stores_nothing(api, session):
    r = api.post("/api/public/tickets", json={**FORM, "website": "http://spam.example"})
    assert r.status_code == 200
    assert r.json() == {"status": "received"}  # no token, no echo of submitted data
    assert count(session, Ticket, subject=FORM["subject"]) == 0
    assert count(session, Customer, email=FORM["email"]) == 0


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_honeypot_is_a_normal_submission(api, session, value):
    form = {**FORM, "email": f"real{len(value or 'x')}@portal.example"}
    if value is not None:
        form["website"] = value
    r = api.post("/api/public/tickets", json=form)
    assert r.status_code == 201, r.text
    assert r.json()["token"]


# --- Absolute link in emails -------------------------------------------------------------


def test_email_link_is_absolute(api, session, agent):
    r = api.post("/api/public/tickets", json=FORM)
    token = r.json()["token"]
    ticket = session.scalars(select(Ticket).where(Ticket.public_token == token)).one()
    h = auth_headers(agent)
    api.post(f"/api/tickets/{ticket.id}/claim", headers=h)
    reply = api.post(f"/api/tickets/{ticket.id}/replies", json={"body": "Looking"}, headers=h)

    session.expire_all()
    ticket = session.get(Ticket, ticket.id)
    email = render_customer_email(ticket, session.get(Message, reply.json()["id"]))
    expected = f"{get_settings().public_base_url}/t/{token}"
    assert expected.startswith(("http://", "https://"))
    assert customer_ticket_url(ticket) == expected
    assert expected in email.body

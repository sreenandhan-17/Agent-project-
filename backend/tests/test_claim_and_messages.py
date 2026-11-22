"""INC-0291: atomic claim, assignee-only replies, internal notes."""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AuditAction,
    AuditEvent,
    Customer,
    Message,
    Priority,
    Ticket,
    TicketStatus,
    Visibility,
)
from app.services.tickets import ClaimOutcome, claim
from app.sla.policy import compute_deadlines
from tests.conftest import audit_actions, auth_headers

YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)


@pytest.fixture
def new_ticket(make_ticket):
    return make_ticket(YESTERDAY, status=TicketStatus.NEW)


@pytest.fixture
def other_agent(make_agent):
    return make_agent()


def claim_url(t):
    return f"/api/tickets/{t.id}/claim"


# --- Claim -------------------------------------------------------------------------------


def test_claim_assigns_opens_and_audits(api, session, agent, new_ticket):
    r = api.post(claim_url(new_ticket), headers=auth_headers(agent))
    assert r.status_code == 200, r.text
    assert r.json()["assignee_id"] == agent.id
    assert r.json()["status"] == "OPEN"
    assert audit_actions(session, new_ticket.id) == ["CLAIMED", "STATUS_CHANGED"]


def test_claim_is_idempotent_for_the_owner(api, session, agent, new_ticket):
    api.post(claim_url(new_ticket), headers=auth_headers(agent))
    r = api.post(claim_url(new_ticket), headers=auth_headers(agent))
    assert r.status_code == 200
    assert audit_actions(session, new_ticket.id) == ["CLAIMED", "STATUS_CHANGED"]


def test_claim_of_taken_ticket_is_409_with_name(api, session, agent, other_agent, new_ticket):
    api.post(claim_url(new_ticket), headers=auth_headers(agent))
    r = api.post(claim_url(new_ticket), headers=auth_headers(other_agent))
    assert r.status_code == 409
    assert r.json() == {"detail": f"Already taken by {agent.name}"}
    session.expire_all()
    assert session.get(Ticket, new_ticket.id).assignee_id == agent.id
    assert audit_actions(session, new_ticket.id).count("CLAIMED") == 1


def test_claim_unknown_ticket_is_404(api, agent):
    assert api.post("/api/tickets/999999/claim", headers=auth_headers(agent)).status_code == 404


def test_claim_requires_auth(api, new_ticket):
    assert api.post(claim_url(new_ticket)).status_code == 401


# --- Replies & notes ---------------------------------------------------------------------


@pytest.fixture
def my_ticket(api, agent, new_ticket):
    assert api.post(claim_url(new_ticket), headers=auth_headers(agent)).status_code == 200
    return new_ticket


def reply(api, ticket, agent, body="Thanks, looking into it."):
    return api.post(f"/api/tickets/{ticket.id}/replies", json={"body": body}, headers=auth_headers(agent))


def note(api, ticket, agent, body="Customer is on the legacy plan."):
    return api.post(f"/api/tickets/{ticket.id}/notes", json={"body": body}, headers=auth_headers(agent))


def test_first_public_reply_sets_first_response_at(api, session, agent, my_ticket):
    r = reply(api, my_ticket, agent)
    assert r.status_code == 201, r.text
    assert r.json()["visibility"] == "PUBLIC"
    session.expire_all()
    first = session.get(Ticket, my_ticket.id).first_response_at
    assert first is not None

    assert reply(api, my_ticket, agent, "Second reply").status_code == 201
    session.expire_all()
    assert session.get(Ticket, my_ticket.id).first_response_at == first
    assert audit_actions(session, my_ticket.id)[-2:] == ["REPLY_SENT", "REPLY_SENT"]


def test_non_assignee_reply_is_403(api, session, other_agent, my_ticket):
    r = reply(api, my_ticket, other_agent)
    assert r.status_code == 403
    assert session.scalar(select(func.count()).where(Message.ticket_id == my_ticket.id)) == 0


def test_reply_on_unassigned_ticket_is_403(api, agent, new_ticket):
    r = reply(api, new_ticket, agent)
    assert r.status_code == 403
    assert "Take the ticket first" in r.json()["detail"]


def test_internal_note_does_not_set_first_response_at(api, session, agent, my_ticket):
    r = note(api, my_ticket, agent)
    assert r.status_code == 201
    assert r.json()["visibility"] == "INTERNAL"
    session.expire_all()
    assert session.get(Ticket, my_ticket.id).first_response_at is None
    assert audit_actions(session, my_ticket.id)[-1] == "NOTE_ADDED"


def test_any_agent_can_add_a_note(api, other_agent, my_ticket):
    assert note(api, my_ticket, other_agent).status_code == 201


def test_empty_reply_rejected(api, agent, my_ticket):
    assert reply(api, my_ticket, agent, "").status_code == 422


# --- Concurrency: needs committed data, so only on a dedicated test DB -------------------


@pytest.fixture
def committed(engine, dedicated_test_db):
    """Two agents and a NEW ticket, really committed (visible to other connections)."""
    if not dedicated_test_db:
        pytest.skip("needs TEST_DATABASE_URL (commits data that can't be cleaned up)")
    tag = uuid.uuid4().hex[:8]
    with Session(engine, expire_on_commit=False) as s:
        a = Agent(name=f"Racer A {tag}", email=f"a-{tag}@race.example", password_hash="x")
        b = Agent(name=f"Racer B {tag}", email=f"b-{tag}@race.example", password_hash="x")
        c = Customer(name="Race Customer", email=f"c-{tag}@race.example")
        s.add_all([a, b, c])
        s.flush()
        t = Ticket(
            subject="race", customer_id=c.id, status=TicketStatus.NEW, priority=Priority.LOW,
            created_at=YESTERDAY, paused_minutes=0, reopen_count=0,
        )
        t.first_response_due_at, t.resolution_due_at = compute_deadlines(t, set())
        s.add(t)
        s.commit()
    return a, b, t


def test_two_simultaneous_http_claims_one_wins(client, engine, committed):
    """INC-0291: two agents press "Take ticket" at the same moment."""
    a, b, ticket = committed
    barrier = threading.Barrier(2)
    results: dict[int, int] = {}

    def press(agent):
        barrier.wait()
        results[agent.id] = client.post(claim_url(ticket), headers=auth_headers(agent)).status_code

    threads = [threading.Thread(target=press, args=(x,)) for x in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert sorted(results.values()) == [200, 409]
    winner = next(aid for aid, code in results.items() if code == 200)
    with Session(engine) as s:
        assert s.get(Ticket, ticket.id).assignee_id == winner
        claims = s.scalars(
            select(AuditEvent).where(
                AuditEvent.ticket_id == ticket.id, AuditEvent.action == AuditAction.CLAIMED
            )
        ).all()
        assert [e.actor_id for e in claims] == [winner]


def test_claim_blocked_mid_transaction_loses(engine, committed):
    """Deterministic race: B claims while A's claim is still uncommitted.

    A check-then-set implementation would let B read assignee_id IS NULL and win too.
    """
    a, b, ticket = committed
    a_claimed, outcome_b = threading.Event(), {}

    def agent_a():
        with Session(engine) as s:
            assert claim(s, ticket.id, s.get(Agent, a.id)).outcome is ClaimOutcome.CLAIMED
            a_claimed.set()
            threading.Event().wait(0.5)  # hold the row lock, uncommitted
            s.commit()

    def agent_b():
        a_claimed.wait(5)
        with Session(engine) as s:
            outcome_b["result"] = claim(s, ticket.id, s.get(Agent, b.id))  # blocks on A's lock
            s.commit()

    ta, tb = threading.Thread(target=agent_a), threading.Thread(target=agent_b)
    ta.start()
    tb.start()
    ta.join(10)
    tb.join(10)

    assert outcome_b["result"].outcome is ClaimOutcome.TAKEN
    assert outcome_b["result"].assignee_name == a.name

"""Step 5 API: list views/filters with SLA state, detail, timeline, agents.

The test DB may contain committed rows from the race tests, so assertions check membership
of this test's own tickets rather than exact result sets.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import AgentRole, CustomerImpact, Priority, TicketStatus
from tests.conftest import auth_headers

S = TicketStatus
NOW = datetime.now(timezone.utc)
LONG_AGO = NOW - timedelta(days=10)


@pytest.fixture
def me(make_agent):
    return make_agent()


@pytest.fixture
def colleague(make_agent):
    return make_agent()


@pytest.fixture
def tickets(make_ticket, me, colleague):
    return {
        "late_mine": make_ticket(LONG_AGO, status=S.OPEN, assignee_id=me.id),
        "waiting_overdue": make_ticket(
            LONG_AGO, status=S.WAITING_ON_CUSTOMER, assignee_id=me.id,
            paused_at=LONG_AGO + timedelta(hours=1),
        ),
        "resolved_overdue": make_ticket(
            LONG_AGO, status=S.RESOLVED, assignee_id=me.id, resolved_at=NOW
        ),
        "fresh_unassigned": make_ticket(NOW, status=S.NEW),
        "triage": make_ticket(
            NOW, status=S.NEW, needs_triage=True, customer_impact=CustomerImpact.PARTIAL
        ),
        "closed_unassigned": make_ticket(LONG_AGO, status=S.CLOSED, closed_at=NOW),
        "colleagues": make_ticket(NOW, status=S.OPEN, assignee_id=colleague.id),
    }


def listed(api, agent, **params) -> dict[int, dict]:
    r = api.get("/api/tickets", params=params, headers=auth_headers(agent))
    assert r.status_code == 200, r.text
    return {row["id"]: row for row in r.json()}


def names(tickets, rows) -> set[str]:
    return {name for name, t in tickets.items() if t.id in rows}


# --- Views -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "view, expected",
    [
        ("mine", {"late_mine", "waiting_overdue", "resolved_overdue"}),
        ("unassigned", {"fresh_unassigned", "triage"}),
        ("late", {"late_mine"}),
        ("waiting", {"waiting_overdue"}),
        ("triage", {"triage"}),
    ],
)
def test_views(api, me, tickets, view, expected):
    assert names(tickets, listed(api, me, view=view)) == expected


def test_all_view_lists_everything(api, me, tickets):
    assert names(tickets, listed(api, me)) == set(tickets)


def test_waiting_ticket_is_never_late(api, me, tickets):
    """notes/11: its stored deadline passed long ago, but the clock is stopped."""
    rows = listed(api, me)
    assert rows[tickets["waiting_overdue"].id]["sla"]["state"] == "paused"
    assert tickets["waiting_overdue"].id not in listed(api, me, view="late")


def test_late_view_matches_red_badges(api, me, tickets):
    rows = listed(api, me)
    late = listed(api, me, view="late")
    for t in tickets.values():
        assert (t.id in late) == (rows[t.id]["sla"]["state"] == "red"), t.id


def test_list_item_shape(api, me, tickets):
    row = listed(api, me)[tickets["late_mine"].id]
    assert row["assignee_name"] == me.name
    assert row["customer_name"].startswith("Test Customer")
    assert row["sla"]["target"] == "first_response"
    assert row["sla"]["remaining_minutes"] < 0
    assert "messages" not in row and "public_token" not in row


def test_filters_combine_with_views(api, me, tickets):
    assert names(tickets, listed(api, me, status="CLOSED")) == {"closed_unassigned"}
    assert names(tickets, listed(api, me, view="mine", status="RESOLVED")) == {"resolved_overdue"}
    assert names(tickets, listed(api, me, priority="URGENT")) == set()


def test_search_by_number_and_subject(api, session, me, tickets):
    t = tickets["triage"]
    assert t.id in listed(api, me, q=t.number)
    t.subject = "Barcode scanner beeps forever"
    session.flush()
    assert names(tickets, listed(api, me, q="barcode SCANNER")) == {"triage"}


def test_closed_tickets_sort_last(api, me, tickets):
    order = [row["id"] for row in listed(api, me).values()]
    assert order.index(tickets["closed_unassigned"].id) > order.index(tickets["late_mine"].id)


def test_unknown_view_rejected(api, me):
    assert api.get("/api/tickets", params={"view": "bogus"}, headers=auth_headers(me)).status_code == 422


# --- Detail ------------------------------------------------------------------------------


def test_detail_includes_internal_notes_for_agents(api, me, tickets):
    t = tickets["late_mine"]
    h = auth_headers(me)
    api.post(f"/api/tickets/{t.id}/notes", json={"body": "Check billing first"}, headers=h)
    api.post(f"/api/tickets/{t.id}/replies", json={"body": "On it"}, headers=h)

    d = api.get(f"/api/tickets/{t.id}", headers=h).json()
    msgs = [(m["visibility"], m["body"], m["author_name"]) for m in d["messages"]]
    assert ("INTERNAL", "Check billing first", me.name) in msgs
    assert ("PUBLIC", "On it", me.name) in msgs
    assert d["customer"]["email"].endswith("@test.example")
    assert d["sla"]["target"] == "resolution"  # first reply now sent


def test_detail_allowed_statuses_follow_permissions(api, me, colleague, make_agent, tickets):
    url = f"/api/tickets/{tickets['late_mine'].id}"
    assert api.get(url, headers=auth_headers(me)).json()["allowed_statuses"] == [
        "RESOLVED", "WAITING_ON_CUSTOMER",
    ]
    assert api.get(url, headers=auth_headers(colleague)).json()["allowed_statuses"] == []
    admin = make_agent(role=AgentRole.ADMIN)
    assert api.get(url, headers=auth_headers(admin)).json()["allowed_statuses"] == [
        "RESOLVED", "WAITING_ON_CUSTOMER",
    ]
    spam = f"/api/tickets/{tickets['fresh_unassigned'].id}"
    assert api.get(spam, headers=auth_headers(colleague)).json()["allowed_statuses"] == ["CLOSED"]


def test_detail_unknown_is_404(api, me):
    assert api.get("/api/tickets/999999", headers=auth_headers(me)).status_code == 404


# --- Timeline ----------------------------------------------------------------------------


def test_timeline_has_actor_names_in_order(api, me, tickets):
    t = tickets["fresh_unassigned"]
    h = auth_headers(me)
    api.post(f"/api/tickets/{t.id}/claim", headers=h)
    api.patch(f"/api/tickets/{t.id}/priority", json={"priority": "URGENT"}, headers=h)
    api.post(f"/api/public/tickets/{t.public_token}/replies", json={"body": "any news?"})

    events = api.get(f"/api/tickets/{t.id}/timeline", headers=h).json()
    assert [(e["action"], e["actor_name"]) for e in events] == [
        ("CLAIMED", me.name),
        ("STATUS_CHANGED", me.name),
        ("PRIORITY_CHANGED", me.name),
        ("CUSTOMER_REPLIED", t.customer.name),
    ]
    assert events[2]["old_value"]["priority"] == "MEDIUM"


def test_timeline_names_the_system(api, session, me, tickets):
    from app.services.audit import Actor
    from app.services.tickets import transition

    t = tickets["waiting_overdue"]
    transition(session, t, S.CLOSED, Actor.system(), holidays=set())
    session.flush()
    events = api.get(f"/api/tickets/{t.id}/timeline", headers=auth_headers(me)).json()
    assert {e["actor_name"] for e in events} == {"System"}


# --- Agents & auth -----------------------------------------------------------------------


def test_agents_lists_active_only(api, session, me, colleague):
    colleague.is_active = False
    session.flush()
    ids = {a["id"] for a in api.get("/api/agents", headers=auth_headers(me)).json()}
    assert me.id in ids and colleague.id not in ids


@pytest.mark.parametrize("path", ["/api/tickets", "/api/tickets/1", "/api/tickets/1/timeline", "/api/agents"])
def test_new_endpoints_require_auth(api, path):
    assert api.get(path).status_code == 401

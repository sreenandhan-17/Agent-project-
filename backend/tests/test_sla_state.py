"""SLA badge state (§8): green / amber (<25% left) / red / paused / done. Pure, no DB.

Reference week (Nov 2026): Fri 20, Sat 21, Sun 22, Mon 23, Thu 26.
"""

from datetime import datetime

import pytest

from app.models import Priority, Ticket, TicketStatus
from app.sla.policy import deadlines_for
from app.sla.state import sla_state
from app.sla.working_hours import TZ

NONE: set = set()


def ist(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def ticket(created, priority=Priority.MEDIUM, status=TicketStatus.OPEN, **fields) -> Ticket:
    first, resolve = deadlines_for(priority, created, 0, NONE)
    return Ticket(
        status=status, priority=priority, created_at=created,
        first_response_due_at=first, resolution_due_at=resolve,
        first_response_at=fields.pop("first_response_at", None),
        paused_at=fields.pop("paused_at", None), **fields,
    )


# MEDIUM created Mon 10:00 -> first reply due Mon 14:30, budget 270 min, amber below 67.5.
MEDIUM_MON = ist(23, 10)


@pytest.mark.parametrize(
    "now, colour, remaining",
    [
        (ist(23, 11), "green", 210),
        (ist(23, 13, 22), "green", 68),  # 68 >= 67.5
        (ist(23, 13, 23), "amber", 67),  # 67 < 67.5
        (ist(23, 14, 29), "amber", 1),
        (ist(23, 14, 30), "red", 0),  # due exactly now = breached
        (ist(23, 16), "red", -90),
    ],
)
def test_first_response_colours(now, colour, remaining):
    s = sla_state(ticket(MEDIUM_MON), now, NONE)
    assert (s.target, s.state, s.remaining_minutes) == ("first_response", colour, remaining)
    assert s.due_at == ist(23, 14, 30)


def test_after_first_reply_badge_tracks_resolution():
    t = ticket(MEDIUM_MON, first_response_at=ist(23, 11))
    s = sla_state(t, ist(23, 16), NONE)  # first-reply deadline passed, but it was met
    assert (s.target, s.state, s.due_at) == ("resolution", "green", ist(26, 10))


def test_overdue_minutes_count_working_time_only():
    t = ticket(ist(20, 10), priority=Priority.URGENT)  # due Fri 12:00
    s = sla_state(t, ist(22, 12), NONE)  # Sunday noon
    assert (s.state, s.remaining_minutes) == ("red", -390)  # 12:00-18:30 Friday only


def test_friday_evening_ticket_is_green_on_sunday():
    s = sla_state(ticket(ist(20, 18), priority=Priority.LOW), ist(22, 12), NONE)
    assert (s.state, s.remaining_minutes) == ("green", 510)


@pytest.mark.parametrize(
    "fields",
    [
        {"status": TicketStatus.WAITING_ON_CUSTOMER, "paused_at": ist(23, 11)},
        {"status": TicketStatus.WAITING_ON_CUSTOMER},
    ],
)
def test_waiting_is_paused_even_when_stored_deadline_passed(fields):
    """notes/11: the stored deadline ignores the running pause; never show red."""
    s = sla_state(ticket(MEDIUM_MON, **fields), ist(30, 18), NONE)
    assert (s.state, s.remaining_minutes) == ("paused", None)


@pytest.mark.parametrize("status", [TicketStatus.RESOLVED, TicketStatus.CLOSED])
def test_resolved_and_closed_have_no_clock(status):
    s = sla_state(ticket(MEDIUM_MON, status=status), ist(30, 18), NONE)
    assert (s.target, s.state, s.due_at, s.remaining_minutes) == (None, "done", None, None)


@pytest.mark.parametrize("status", [TicketStatus.NEW, TicketStatus.REOPENED])
def test_other_active_statuses_run_the_clock(status):
    assert sla_state(ticket(MEDIUM_MON, status=status), ist(23, 16), NONE).state == "red"

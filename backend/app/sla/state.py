"""SLA badge state for the agent UI (PROJECT_SUMMARY.md §8, notes/11).

The badge tracks the next pending deadline: first reply until one is sent, then resolution.
  red    = deadline passed
  amber  = less than 25% of the working-time budget left
  green  = on track
  paused = waiting on customer (clock stopped; never late, whatever the stored deadline says)
  done   = resolved or closed (no clock)
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.models import Ticket, TicketStatus
from app.sla.working_hours import working_minutes_between

AMBER_FRACTION = 0.25

SlaTarget = Literal["first_response", "resolution"]
SlaColour = Literal["green", "amber", "red", "paused", "done"]

# Statuses whose SLA clock is running. Used by the Late filter too.
ACTIVE_STATUSES = (TicketStatus.NEW, TicketStatus.OPEN, TicketStatus.REOPENED)


@dataclass(frozen=True)
class SlaState:
    target: SlaTarget | None
    due_at: datetime | None
    state: SlaColour
    remaining_minutes: int | None  # working minutes; negative = overdue by that much


def _target(ticket: Ticket) -> tuple[SlaTarget, datetime | None]:
    if ticket.first_response_at is None:
        return "first_response", ticket.first_response_due_at
    return "resolution", ticket.resolution_due_at


def sla_state(ticket: Ticket, now: datetime, holidays: set[date]) -> SlaState:
    if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        return SlaState(None, None, "done", None)

    target, due = _target(ticket)
    if ticket.paused_at is not None or ticket.status is TicketStatus.WAITING_ON_CUSTOMER:
        return SlaState(target, due, "paused", None)
    if due is None:
        return SlaState(target, None, "green", None)

    if now >= due:
        overdue = working_minutes_between(due, now, holidays)
        return SlaState(target, due, "red", -overdue)

    remaining = working_minutes_between(now, due, holidays)
    # Budget = working time from creation to this deadline (includes past pauses).
    budget = working_minutes_between(ticket.created_at, due, holidays)
    colour: SlaColour = "amber" if budget and remaining < budget * AMBER_FRACTION else "green"
    return SlaState(target, due, colour, remaining)

"""SLA targets per priority and deadline computation. See PROJECT_SUMMARY.md §3.1, §3.3, §3.6."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Holiday, Priority, Ticket
from app.sla.working_hours import add_working_minutes, end_of_working_day

# priority -> (first reply, resolution) in working minutes.
# Resolution None means "by the end of the same working day" (URGENT).
SLA_MINUTES: dict[Priority, tuple[int, int | None]] = {
    Priority.URGENT: (120, None),
    Priority.MEDIUM: (270, 1620),
    Priority.LOW: (540, 2700),
}


def deadlines_for(
    priority: Priority, created_at: datetime, paused_minutes: int, holidays: set[date]
) -> tuple[datetime, datetime]:
    """(first_response_due_at, resolution_due_at), counted from created_at.

    Paused working minutes push both deadlines later. Recomputing from created_at with a new
    priority is how a mid-way priority change works (§3.6), so it may already be in the past.
    """
    first_minutes, resolve_minutes = SLA_MINUTES[priority]
    first_due = add_working_minutes(created_at, first_minutes + paused_minutes, holidays)

    if resolve_minutes is None:
        resolve_due = add_working_minutes(
            end_of_working_day(created_at, holidays), paused_minutes, holidays
        )
        # §3.1 assumption: resolution is never due before the first reply.
        resolve_due = max(resolve_due, first_due)
    else:
        resolve_due = add_working_minutes(created_at, resolve_minutes + paused_minutes, holidays)

    return first_due, resolve_due


def compute_deadlines(ticket: Ticket, holidays: set[date]) -> tuple[datetime, datetime]:
    return deadlines_for(ticket.priority, ticket.created_at, ticket.paused_minutes or 0, holidays)


def load_holidays(session: Session) -> set[date]:
    return set(session.scalars(select(Holiday.date)))

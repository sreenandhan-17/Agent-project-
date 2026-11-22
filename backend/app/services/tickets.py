"""Ticket state changes. See PROJECT_SUMMARY.md §3.3, §3.6, §5.

Every status change goes through transition(); every priority change through change_priority().
Both write their audit events in the caller's transaction and never commit.
"""

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import AuditAction, Priority, Ticket, TicketStatus
from app.services.audit import Actor, record
from app.sla.policy import compute_deadlines, load_holidays
from app.sla.working_hours import working_minutes_between

S = TicketStatus

ALLOWED_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    S.NEW: frozenset({S.OPEN, S.CLOSED}),
    S.OPEN: frozenset({S.WAITING_ON_CUSTOMER, S.RESOLVED}),
    S.WAITING_ON_CUSTOMER: frozenset({S.OPEN, S.RESOLVED, S.CLOSED}),
    S.RESOLVED: frozenset({S.CLOSED, S.REOPENED}),
    S.CLOSED: frozenset({S.REOPENED}),
    S.REOPENED: frozenset({S.WAITING_ON_CUSTOMER, S.RESOLVED}),
}


class InvalidTransition(Exception):
    def __init__(self, from_status: TicketStatus, to_status: TicketStatus):
        self.from_status = from_status
        self.to_status = to_status
        self.allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[from_status])
        super().__init__(f"cannot move ticket from {from_status.value} to {to_status.value}")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _deadlines(ticket: Ticket) -> dict[str, str | None]:
    return {
        "first_response_due_at": _iso(ticket.first_response_due_at),
        "resolution_due_at": _iso(ticket.resolution_due_at),
    }


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _resume_sla(
    session: Session, ticket: Ticket, actor: Actor, now: datetime, holidays: set[date]
) -> None:
    """Close the current pause: add its working minutes and shift deadlines by them (§3.3)."""
    paused = working_minutes_between(ticket.paused_at, now, holidays)
    old = {"paused_minutes": ticket.paused_minutes, **_deadlines(ticket)}
    ticket.paused_minutes = (ticket.paused_minutes or 0) + paused
    ticket.paused_at = None
    ticket.first_response_due_at, ticket.resolution_due_at = compute_deadlines(ticket, holidays)
    new = {"paused_minutes": ticket.paused_minutes, **_deadlines(ticket)}
    record(session, ticket.id, actor, AuditAction.SLA_RESUMED, "paused_minutes", old, new)


def transition(
    session: Session,
    ticket: Ticket,
    to_status: TicketStatus,
    actor: Actor,
    *,
    now: datetime | None = None,
    holidays: set[date] | None = None,
) -> None:
    """Validate and apply a status change, with SLA pause/resume. Raises InvalidTransition."""
    from_status = ticket.status
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise InvalidTransition(from_status, to_status)

    now = _now(now)
    if holidays is None:
        holidays = load_holidays(session)

    ticket.status = to_status
    record(
        session, ticket.id, actor, AuditAction.STATUS_CHANGED, "status",
        from_status.value, to_status.value,
    )

    if from_status is S.WAITING_ON_CUSTOMER and ticket.paused_at is not None:
        _resume_sla(session, ticket, actor, now, holidays)

    if to_status is S.WAITING_ON_CUSTOMER:
        ticket.paused_at = now
        record(session, ticket.id, actor, AuditAction.SLA_PAUSED, "paused_at", None, _iso(now))
    elif to_status is S.RESOLVED:
        ticket.resolved_at = now
    elif to_status is S.CLOSED:
        ticket.closed_at = now
    elif to_status is S.REOPENED:
        # 7-day window and fresh resolution deadline come in build step 7 (notes/09).
        ticket.reopen_count = (ticket.reopen_count or 0) + 1
        ticket.resolved_at = None
        ticket.closed_at = None


def change_priority(
    session: Session,
    ticket: Ticket,
    new_priority: Priority,
    actor: Actor,
    *,
    holidays: set[date] | None = None,
) -> bool:
    """Recompute deadlines from created_at with the new priority (§3.6). False if unchanged.

    The new deadlines may already be in the past; the ticket is then breached immediately.
    """
    if new_priority is ticket.priority:
        return False
    if holidays is None:
        holidays = load_holidays(session)

    old = {"priority": ticket.priority.value, **_deadlines(ticket)}
    ticket.priority = new_priority
    ticket.first_response_due_at, ticket.resolution_due_at = compute_deadlines(ticket, holidays)
    new = {"priority": new_priority.value, **_deadlines(ticket)}
    record(session, ticket.id, actor, AuditAction.PRIORITY_CHANGED, "priority", old, new)
    return True

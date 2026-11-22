"""Ticket list queries for the agent UI (PROJECT_SUMMARY.md §8)."""

from datetime import datetime
from typing import Literal

from sqlalchemy import Select, and_, case, or_, select
from sqlalchemy.orm import selectinload

from app.models import Customer, Priority, Ticket, TicketStatus
from app.sla.state import ACTIVE_STATUSES

TicketView = Literal["all", "mine", "unassigned", "late", "waiting", "triage"]

CLOSED_STATUSES = (TicketStatus.RESOLVED, TicketStatus.CLOSED)

# The deadline the SLA badge tracks: first reply until sent, then resolution (see sla/state.py).
next_due = case(
    (Ticket.first_response_at.is_(None), Ticket.first_response_due_at),
    else_=Ticket.resolution_due_at,
)


def late_condition(now: datetime):
    """Clock running AND the tracked deadline has passed. Must agree with sla_state() == "red".

    Waiting-on-customer, resolved and closed tickets are never late: their stored deadlines
    don't include an in-progress pause (notes/11).
    """
    return and_(
        Ticket.status.in_(ACTIVE_STATUSES),
        Ticket.paused_at.is_(None),
        next_due <= now,
    )


def ticket_list_query(
    view: TicketView,
    *,
    agent_id: int,
    now: datetime,
    status: TicketStatus | None = None,
    priority: Priority | None = None,
    needs_triage: bool | None = None,
    q: str | None = None,
) -> Select[tuple[Ticket]]:
    stmt = select(Ticket).options(
        selectinload(Ticket.customer), selectinload(Ticket.assignee)
    )

    if view == "mine":
        stmt = stmt.where(Ticket.assignee_id == agent_id)
    elif view == "unassigned":
        stmt = stmt.where(Ticket.assignee_id.is_(None), Ticket.status.not_in(CLOSED_STATUSES))
    elif view == "late":
        stmt = stmt.where(late_condition(now))
    elif view == "waiting":
        stmt = stmt.where(Ticket.status == TicketStatus.WAITING_ON_CUSTOMER)
    elif view == "triage":
        stmt = stmt.where(Ticket.needs_triage.is_(True), Ticket.status.not_in(CLOSED_STATUSES))

    if status is not None:
        stmt = stmt.where(Ticket.status == status)
    if priority is not None:
        stmt = stmt.where(Ticket.priority == priority)
    if needs_triage is not None:
        stmt = stmt.where(Ticket.needs_triage.is_(needs_triage))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.join(Ticket.customer).where(
            or_(Ticket.number.ilike(like), Ticket.subject.ilike(like), Customer.name.ilike(like))
        )

    closed_last = case((Ticket.status.in_(CLOSED_STATUSES), 1), else_=0)
    return stmt.order_by(closed_last, next_due.asc().nulls_last(), Ticket.id.desc())

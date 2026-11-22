from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_agent
from app.models import (
    Agent,
    AuditAction,
    AuditEvent,
    AuthorType,
    CustomerImpact,
    Priority,
    Ticket,
    TicketStatus,
    Visibility,
)
from app.serializers.customer import render_transcript, serialize_for_customer
from app.services.audit import Actor
from app.services.email import send_customer_email
from app.sla.policy import load_holidays
from app.sla.state import sla_state
from app.services.queries import TicketView, ticket_list_query
from app.services.tickets import (
    ALLOWED_TRANSITIONS,
    ClaimOutcome,
    InvalidTransition,
    NotAssignee,
    add_note,
    add_reply,
    change_priority,
    claim,
    may_change_status,
    transition,
)

# Every route here is agent-only.
router = APIRouter(
    prefix="/api/tickets", tags=["tickets"], dependencies=[Depends(get_current_agent)]
)


class StatusChange(BaseModel):
    status: TicketStatus


class PriorityChange(BaseModel):
    priority: Priority


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    subject: str
    status: TicketStatus
    priority: Priority
    assignee_id: int | None
    created_at: datetime
    first_response_at: datetime | None
    first_response_due_at: datetime | None
    resolution_due_at: datetime | None
    paused_at: datetime | None
    paused_minutes: int
    resolved_at: datetime | None
    closed_at: datetime | None
    reopen_count: int
    needs_triage: bool
    customer_impact: CustomerImpact | None


class MessageOut(BaseModel):
    """Agent-side message view: includes INTERNAL notes. Never send to customers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author_type: AuthorType
    author_agent_id: int | None
    visibility: Visibility
    body: str
    created_at: datetime


class SlaOut(BaseModel):
    target: Literal["first_response", "resolution"] | None
    due_at: datetime | None
    state: Literal["green", "amber", "red", "paused", "done"]
    remaining_minutes: int | None


class TicketListItem(TicketOut):
    customer_name: str
    assignee_name: str | None
    sla: SlaOut


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None
    company: str | None


class AgentMessageOut(MessageOut):
    author_name: str


class TicketDetail(TicketListItem):
    customer: CustomerOut
    public_token: str
    parent_ticket_number: str | None
    allowed_statuses: list[TicketStatus]  # transitions THIS agent may make now
    messages: list[AgentMessageOut]


class TimelineEvent(BaseModel):
    id: int
    action: AuditAction
    field: str | None
    old_value: Any
    new_value: Any
    created_at: datetime
    actor_type: AuthorType
    actor_id: int | None
    actor_name: str


def _list_item(ticket: Ticket, now: datetime, holidays: set) -> TicketListItem:
    return TicketListItem(
        **TicketOut.model_validate(ticket).model_dump(),
        customer_name=ticket.customer.name,
        assignee_name=ticket.assignee.name if ticket.assignee else None,
        sla=SlaOut(**asdict(sla_state(ticket, now, holidays))),
    )


def _get_ticket(session: Session, ticket_id: int, *, lock: bool = False) -> Ticket:
    # Row lock (lock=True) so two concurrent changes to one ticket apply one after the other.
    ticket = session.get(Ticket, ticket_id, with_for_update=lock)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    return ticket


@router.get("", response_model=list[TicketListItem])
def list_tickets(
    view: TicketView = "all",
    status_: TicketStatus | None = Query(default=None, alias="status"),
    priority: Priority | None = None,
    needs_triage: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, ge=1, le=500),
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    """Agent ticket list: active tickets first, most urgent deadline first.

    Views: all | mine | unassigned | late | waiting | triage. "late" never includes tickets
    that are waiting on the customer, resolved or closed (notes/11).
    """
    now = datetime.now(timezone.utc)
    stmt = ticket_list_query(
        view, agent_id=agent.id, now=now, status=status_, priority=priority,
        needs_triage=needs_triage, q=q,
    ).limit(limit)
    holidays = load_holidays(session)
    return [_list_item(t, now, holidays) for t in session.scalars(stmt)]


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(
    ticket_id: int,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    """Agent ticket detail. Includes INTERNAL notes: agent-only, never for customers."""
    ticket = _get_ticket(session, ticket_id)
    now = datetime.now(timezone.utc)
    holidays = load_holidays(session)
    agents = {a.id: a.name for a in session.scalars(select(Agent))}
    parent = session.get(Ticket, ticket.parent_ticket_id) if ticket.parent_ticket_id else None
    item = _list_item(ticket, now, holidays)
    return TicketDetail(
        **item.model_dump(),
        customer=CustomerOut.model_validate(ticket.customer),
        public_token=ticket.public_token,
        parent_ticket_number=parent.number if parent else None,
        allowed_statuses=sorted(
            (s for s in ALLOWED_TRANSITIONS[ticket.status] if may_change_status(ticket, agent, s)),
            key=lambda s: s.value,
        ),
        messages=[
            AgentMessageOut(
                **MessageOut.model_validate(m).model_dump(),
                author_name=(
                    ticket.customer.name
                    if m.author_type is AuthorType.CUSTOMER
                    else agents.get(m.author_agent_id, "System")
                ),
            )
            for m in sorted(ticket.messages, key=lambda m: m.id)
        ],
    )


@router.get("/{ticket_id}/timeline", response_model=list[TimelineEvent])
def get_timeline(ticket_id: int, session: Session = Depends(get_session)):
    """Audit trail for one ticket, oldest first (INC-0318)."""
    ticket = _get_ticket(session, ticket_id)
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.ticket_id == ticket.id).order_by(AuditEvent.id)
    ).all()
    agents = {a.id: a.name for a in session.scalars(select(Agent))}

    def actor_name(e: AuditEvent) -> str:
        if e.actor_type is AuthorType.SYSTEM:
            return "System"
        if e.actor_type is AuthorType.CUSTOMER:
            return ticket.customer.name if e.actor_id == ticket.customer_id else "Customer"
        return agents.get(e.actor_id, f"Agent #{e.actor_id}")

    return [
        TimelineEvent(
            id=e.id, action=e.action, field=e.field, old_value=e.old_value,
            new_value=e.new_value, created_at=e.created_at, actor_type=e.actor_type,
            actor_id=e.actor_id, actor_name=actor_name(e),
        )
        for e in events
    ]


@router.patch("/{ticket_id}/status", response_model=TicketOut)
def update_status(
    ticket_id: int,
    body: StatusChange,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    ticket = _get_ticket(session, ticket_id, lock=True)
    if not may_change_status(ticket, agent, body.status):
        session.rollback()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the assignee or an admin can change this ticket's status.",
        )
    try:
        transition(session, ticket, body.status, Actor.agent(agent.id))
    except InvalidTransition as e:
        session.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": str(e), "from": e.from_status.value, "allowed": e.allowed},
        )
    session.commit()
    return ticket


@router.patch("/{ticket_id}/priority", response_model=TicketOut)
def update_priority(
    ticket_id: int,
    body: PriorityChange,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    # Any active agent may re-prioritise (triage); audited with old/new deadlines (Ã‚Â§4).
    ticket = _get_ticket(session, ticket_id, lock=True)
    change_priority(session, ticket, body.priority, Actor.agent(agent.id))
    session.commit()
    return ticket


@router.post("/{ticket_id}/claim", response_model=TicketOut)
def claim_ticket(
    ticket_id: int,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    result = claim(session, ticket_id, agent)
    if result.outcome is ClaimOutcome.NOT_FOUND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    if result.outcome is ClaimOutcome.TAKEN:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already taken by {result.assignee_name}")
    session.commit()
    return _get_ticket(session, ticket_id)


@router.post("/{ticket_id}/replies", response_model=MessageOut, status_code=201)
def reply(
    ticket_id: int,
    body: MessageIn,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    ticket = _get_ticket(session, ticket_id, lock=True)
    try:
        message = add_reply(session, ticket, agent, body.body)
    except NotAssignee:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the assignee can reply. Take the ticket first."
            if ticket.assignee_id is None
            else "Only the assignee can reply.",
        )
    session.commit()
    session.refresh(ticket, ["messages"])
    send_customer_email(ticket, message)
    return message


@router.post("/{ticket_id}/notes", response_model=MessageOut, status_code=201)
def note(
    ticket_id: int,
    body: MessageIn,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    ticket = _get_ticket(session, ticket_id)
    message = add_note(session, ticket, agent, body.body)
    session.commit()
    return message


@router.get("/{ticket_id}/export", response_class=PlainTextResponse)
def export_transcript(ticket_id: int, session: Session = Depends(get_session)):
    """Customer-facing transcript: built from serialize_for_customer(), so no internal notes."""
    ticket = _get_ticket(session, ticket_id)
    return render_transcript(serialize_for_customer(ticket, ticket.messages))

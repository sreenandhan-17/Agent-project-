from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_agent
from app.models import (
    Agent,
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
from app.services.tickets import (
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


def _get_ticket(session: Session, ticket_id: int, *, lock: bool = False) -> Ticket:
    # Row lock (lock=True) so two concurrent changes to one ticket apply one after the other.
    ticket = session.get(Ticket, ticket_id, with_for_update=lock)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    return ticket


@router.get("", response_model=list[TicketOut])
def list_tickets(
    needs_triage: bool | None = None,
    session: Session = Depends(get_session),
):
    """Agent ticket list, newest first. Views, filters and SLA badges come in step 5."""
    stmt = select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc())
    if needs_triage is not None:
        stmt = stmt.where(Ticket.needs_triage.is_(needs_triage))
    return session.scalars(stmt).all()


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
    # Any active agent may re-prioritise (triage); audited with old/new deadlines (Â§4).
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

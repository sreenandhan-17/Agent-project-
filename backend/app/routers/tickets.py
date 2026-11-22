from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_agent
from app.models import Agent, Priority, Ticket, TicketStatus
from app.services.audit import Actor
from app.services.tickets import InvalidTransition, change_priority, transition

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


class StatusChange(BaseModel):
    status: TicketStatus


class PriorityChange(BaseModel):
    priority: Priority


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    subject: str
    status: TicketStatus
    priority: Priority
    assignee_id: int | None
    created_at: datetime
    first_response_due_at: datetime | None
    resolution_due_at: datetime | None
    paused_at: datetime | None
    paused_minutes: int
    resolved_at: datetime | None
    closed_at: datetime | None
    reopen_count: int


def _locked_ticket(session: Session, ticket_id: int) -> Ticket:
    # Row lock so two concurrent changes to one ticket apply one after the other.
    ticket = session.get(Ticket, ticket_id, with_for_update=True)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    return ticket


@router.patch("/{ticket_id}/status", response_model=TicketOut)
def update_status(
    ticket_id: int,
    body: StatusChange,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_current_agent),
):
    ticket = _locked_ticket(session, ticket_id)
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
    ticket = _locked_ticket(session, ticket_id)
    change_priority(session, ticket, body.priority, Actor.agent(agent.id))
    session.commit()
    return ticket

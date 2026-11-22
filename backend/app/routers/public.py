"""Customer-facing routes (INC-0304). No auth: the unguessable public_token is the credential.

Every response here MUST be a CustomerTicketView from serialize_for_customer().
tests/test_no_leaks.py fails if a route is added here without being leak-tested.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import CustomerImpact, Ticket
from app.serializers.customer import CustomerTicketView, serialize_for_customer
from app.services.tickets import add_customer_reply, create_customer_ticket

router = APIRouter(prefix="/api/public", tags=["public"])


class NewTicketIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    company: str | None = Field(default=None, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)
    impact: CustomerImpact  # "I can't work" / "partly affected" / "just a question"


class CustomerReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class NewTicketOut(BaseModel):
    token: str  # the customer's link to this ticket
    ticket: CustomerTicketView


def _ticket_by_token(session: Session, token: str, *, lock: bool = False) -> Ticket:
    stmt = select(Ticket).where(Ticket.public_token == token)
    if lock:
        stmt = stmt.with_for_update()
    ticket = session.scalars(stmt).one_or_none()
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    return ticket


@router.post("/tickets", response_model=NewTicketOut, status_code=201)
def submit_ticket(body: NewTicketIn, session: Session = Depends(get_session)):
    ticket = create_customer_ticket(
        session,
        name=body.name,
        email=body.email,
        phone=body.phone,
        company=body.company,
        subject=body.subject,
        body=body.body,
        customer_impact=body.impact,
    )
    session.commit()
    session.refresh(ticket, ["messages"])
    return NewTicketOut(
        token=ticket.public_token, ticket=serialize_for_customer(ticket, ticket.messages)
    )


@router.get("/tickets/{token}", response_model=CustomerTicketView)
def view_ticket(token: str, session: Session = Depends(get_session)):
    ticket = _ticket_by_token(session, token)
    return serialize_for_customer(ticket, ticket.messages)


@router.post("/tickets/{token}/replies", response_model=CustomerTicketView, status_code=201)
def customer_reply(token: str, body: CustomerReplyIn, session: Session = Depends(get_session)):
    ticket = _ticket_by_token(session, token, lock=True)
    add_customer_reply(session, ticket, body.body)
    session.commit()
    session.refresh(ticket, ["messages"])
    return serialize_for_customer(ticket, ticket.messages)

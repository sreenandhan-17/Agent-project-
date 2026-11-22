"""Customer-facing routes (INC-0304). No auth: the unguessable public_token is the credential.

Every response here MUST be a CustomerTicketView from serialize_for_customer().
tests/test_no_leaks.py fails if a route is added here without being leak-tested.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import CustomerImpact, Ticket
from app.serializers.customer import CustomerTicketView, serialize_for_customer
from app.services.tickets import add_customer_reply, create_customer_ticket

router = APIRouter(prefix="/api/public", tags=["public"])
log = logging.getLogger("frontdesk.public")


class NewTicketIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    company: str | None = Field(default=None, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)
    impact: CustomerImpact  # "I can't work" / "partly affected" / "just a question"
    # Honeypot (notes/14): hidden from people by the form; bots that fill every field fill it.
    website: str | None = Field(default=None, max_length=500)


class CustomerReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class NewTicketOut(BaseModel):
    token: str  # the customer's link to this ticket
    ticket: CustomerTicketView


class ReplyOut(BaseModel):
    # Same shape as NewTicketOut, named for this route: `token` is the token to use going
    # forward. It's usually the same token the customer already has, but differs when the
    # reply landed on a new follow-up ticket instead (§3.5) — the frontend must redirect there.
    token: str
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
    if body.website and body.website.strip():
        # Looks like success to the bot; nothing is stored and no customer data is echoed.
        log.info("public ticket dropped: honeypot field filled")
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "received"})
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


@router.post("/tickets/{token}/replies", response_model=ReplyOut, status_code=201)
def customer_reply(token: str, body: CustomerReplyIn, session: Session = Depends(get_session)):
    ticket = _ticket_by_token(session, token, lock=True)
    resulting_ticket, _message = add_customer_reply(session, ticket, body.body)
    session.commit()
    session.refresh(resulting_ticket, ["messages"])
    return ReplyOut(
        token=resulting_ticket.public_token,
        ticket=serialize_for_customer(resulting_ticket, resulting_ticket.messages),
    )

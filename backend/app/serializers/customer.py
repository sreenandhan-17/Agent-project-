"""INC-0304: the ONLY way ticket data reaches a customer.

Every customer-facing output (public API, transcript export, email) is built from
serialize_for_customer(). It copies an explicit allow-list of fields and keeps PUBLIC
messages only, so a new column or message type stays hidden until added here on purpose.
"""

from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import AuthorType, Message, Ticket, TicketStatus, Visibility

SUPPORT_DISPLAY_NAME = "Arvo Support"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CustomerMessage(_Strict):
    id: int
    author: str  # "customer" | "support"
    author_name: str
    body: str
    created_at: datetime


class CustomerTicketView(_Strict):
    number: str
    subject: str
    status: TicketStatus
    created_at: datetime
    messages: list[CustomerMessage]


def _customer_message(ticket: Ticket, m: Message) -> CustomerMessage:
    from_customer = m.author_type is AuthorType.CUSTOMER
    return CustomerMessage(
        id=m.id,
        author="customer" if from_customer else "support",
        # Agent names stay internal; customers see the team name.
        author_name=ticket.customer.name if from_customer else SUPPORT_DISPLAY_NAME,
        body=m.body,
        created_at=m.created_at,
    )


def serialize_for_customer(ticket: Ticket, messages: Iterable[Message]) -> CustomerTicketView:
    return CustomerTicketView(
        number=ticket.number,
        subject=ticket.subject,
        status=ticket.status,
        created_at=ticket.created_at,
        messages=[
            _customer_message(ticket, m)
            for m in sorted(messages, key=lambda m: m.id)
            if m.visibility is Visibility.PUBLIC
        ],
    )


def render_transcript(view: CustomerTicketView) -> str:
    """Plain-text transcript for export. Takes the serialized view, never the ORM ticket."""
    lines = [f"{view.number}: {view.subject}", f"Status: {view.status.value}", ""]
    for m in view.messages:
        lines += [f"[{m.created_at.isoformat()}] {m.author_name}:", m.body, ""]
    return "\n".join(lines)

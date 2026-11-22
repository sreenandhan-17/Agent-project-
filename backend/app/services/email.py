"""Customer email rendering. Emails are logged, not sent (PROJECT_SUMMARY.md §1, out of scope)."""

import logging
from dataclasses import dataclass

from app.config import get_settings
from app.models import Message, Ticket
from app.serializers.customer import serialize_for_customer

log = logging.getLogger("frontdesk.email")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


def customer_ticket_url(ticket: Ticket) -> str:
    """Absolute link to the customer's ticket page (frontend route /t/:token)."""
    return f"{get_settings().public_base_url}/t/{ticket.public_token}"


def render_customer_email(ticket: Ticket, message: Message) -> Email:
    """Notification for a new PUBLIC message. Built from serialize_for_customer() only.

    Raises ValueError if `message` is not in the customer view (i.e. it is INTERNAL).
    """
    view = serialize_for_customer(ticket, ticket.messages)
    shown = next((m for m in view.messages if m.id == message.id), None)
    if shown is None:
        raise ValueError("refusing to email a message the customer cannot see")

    body = "\n".join(
        [
            f"Hi {ticket.customer.name},",
            "",
            f"{shown.author_name} replied to your ticket {view.number} ({view.subject}):",
            "",
            shown.body,
            "",
            f"Status: {view.status.value}",
            f"View the conversation and reply: {customer_ticket_url(ticket)}",
        ]
    )
    return Email(to=ticket.customer.email, subject=f"[{view.number}] {view.subject}", body=body)


def send_customer_email(ticket: Ticket, message: Message) -> Email:
    email = render_customer_email(ticket, message)
    log.info("email (not sent) to=%s subject=%s", email.to, email.subject)
    return email

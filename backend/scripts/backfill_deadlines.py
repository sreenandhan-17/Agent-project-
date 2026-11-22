"""Fill in missing SLA deadlines on existing tickets (notes/01). Idempotent.

Only touches tickets where first_response_due_at or resolution_due_at is NULL, so deadlines
already set (e.g. after a priority change) are never overwritten.

Usage (from /backend):  python -m scripts.backfill_deadlines
"""

from sqlalchemy import or_, select

from app.db import get_sessionmaker
from app.models import Ticket
from app.sla.policy import compute_deadlines, load_holidays


def main() -> None:
    with get_sessionmaker()() as session, session.begin():
        hols = load_holidays(session)
        tickets = session.scalars(
            select(Ticket).where(
                or_(Ticket.first_response_due_at.is_(None), Ticket.resolution_due_at.is_(None))
            )
        ).all()
        for ticket in tickets:
            ticket.first_response_due_at, ticket.resolution_due_at = compute_deadlines(ticket, hols)
    print(f"Backfilled deadlines on {len(tickets)} ticket(s).")


if __name__ == "__main__":
    main()

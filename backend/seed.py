"""Seed demo data. Safe to run repeatedly: existing rows are left alone.

Usage (from /backend):
  SEED_AGENT_PASSWORD="<password>" python seed.py        # macOS/Linux/bash
  $env:SEED_AGENT_PASSWORD="<password>"; python seed.py   # PowerShell

The real demo password is never committed to this repo (it was once, and got rotated —
don't repeat that). It's only ever passed inline on the command line, like DATABASE_URL
already is for production seeding; see DEPLOY.md. With ENV=dev and the variable unset, a
clearly-fake local-only placeholder is used instead, so local dev still works with no setup.
"""

import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.db import get_sessionmaker
from app.models import (
    Agent,
    AgentRole,
    AuditAction,
    AuthorType,
    Customer,
    CustomerImpact,
    Holiday,
    Message,
    Priority,
    Ticket,
    TicketStatus,
    Visibility,
)
from app.services.audit import record_event
from app.sla.policy import compute_deadlines, load_holidays

_DEV_ONLY_PASSWORD = "dev-only-seed-password-do-not-use-in-production"


def _demo_password() -> str:
    # os.environ, not Settings().seed_agent_password: this must work whether SEED_AGENT_PASSWORD
    # is a real shell env var or came from backend/.env, same as DATABASE_URL etc. get_settings()
    # is only used for is_dev, so this honors ENV=dev from a .env file the same way the rest of
    # the app does, rather than requiring ENV to be exported separately from the .env file.
    password = os.environ.get("SEED_AGENT_PASSWORD")
    if password:
        return password
    if get_settings().is_dev:
        return _DEV_ONLY_PASSWORD
    raise SystemExit(
        "SEED_AGENT_PASSWORD is not set (required unless ENV=dev). Pick a password and pass "
        "it inline, the same way DATABASE_URL is passed for production seeding — never commit "
        "it. Example: SEED_AGENT_PASSWORD=\"...\" python seed.py"
    )


DEMO_PASSWORD = _demo_password()

AGENTS = [
    ("Ananya Rao", "ananya@arvo.example", AgentRole.ADMIN),
    ("Rahul Menon", "rahul@arvo.example", AgentRole.AGENT),
    ("Priya Nair", "priya@arvo.example", AgentRole.AGENT),
    ("Vikram Shah", "vikram@arvo.example", AgentRole.AGENT),
    ("Meera Iyer", "meera@arvo.example", AgentRole.AGENT),
    ("Arjun Pillai", "arjun@arvo.example", AgentRole.AGENT),
    ("Sneha Kulkarni", "sneha@arvo.example", AgentRole.AGENT),
    ("Karthik Reddy", "karthik@arvo.example", AgentRole.AGENT),
    ("Divya Joshi", "divya@arvo.example", AgentRole.AGENT),
]

CUSTOMERS = [
    ("Neha Gupta", "neha@lumenretail.example", "+91 98450 11223", "Lumen Retail"),
    ("Sanjay Verma", "sanjay@bluepeak.example", "+91 99001 44556", "BluePeak Logistics"),
    ("Fatima Sheikh", "fatima@greenleaf.example", "+91 90080 77889", "GreenLeaf Foods"),
    ("Rohan Das", "rohan@nimbusedu.example", "+91 98860 33445", "Nimbus Education"),
    ("Lakshmi Krishnan", "lakshmi@orbitclinics.example", "+91 97400 66778", "Orbit Clinics"),
]

# 2026 gazetted holidays for Central Government offices (DoPT OM F.No.12/2/2023-JCA, 03-07-2025).
# Source: https://dfe.gov.in/uploads/documents/list-of-gazetted-holidays-2026.pdf
# Replace with Arvo's own holiday list if it differs.
HOLIDAYS = [
    (date(2026, 1, 26), "Republic Day"),
    (date(2026, 3, 4), "Holi"),
    (date(2026, 3, 21), "Id-ul-Fitr"),
    (date(2026, 3, 26), "Ram Navami"),
    (date(2026, 3, 31), "Mahavir Jayanti"),
    (date(2026, 4, 3), "Good Friday"),
    (date(2026, 5, 1), "Buddha Purnima"),
    (date(2026, 5, 27), "Id-ul-Zuha (Bakrid)"),
    (date(2026, 6, 26), "Muharram"),
    (date(2026, 8, 15), "Independence Day"),
    (date(2026, 8, 26), "Milad-un-Nabi"),
    (date(2026, 9, 4), "Janmashtami"),
    (date(2026, 10, 2), "Gandhi Jayanti"),
    (date(2026, 10, 20), "Dussehra"),
    (date(2026, 11, 8), "Diwali"),
    (date(2026, 11, 24), "Guru Nanak's Birthday"),
    (date(2026, 12, 25), "Christmas"),
]

IMPACT_HINT = {
    Priority.URGENT: CustomerImpact.CANNOT_WORK,
    Priority.MEDIUM: CustomerImpact.PARTIAL,
    Priority.LOW: CustomerImpact.QUESTION,
}

# (subject, customer index, priority, status, assignee index or None, hours ago)
TICKETS = [
    ("POS terminals not syncing sales since morning", 0, Priority.URGENT, TicketStatus.NEW, None, 1),
    ("Invoice PDF shows wrong GST number", 1, Priority.MEDIUM, TicketStatus.NEW, None, 3),
    ("Cannot reset password for store manager", 0, Priority.LOW, TicketStatus.OPEN, 1, 6),
    ("Delivery tracking page loads blank", 1, Priority.URGENT, TicketStatus.OPEN, 2, 2),
    ("Need export of last quarter's orders", 2, Priority.LOW, TicketStatus.WAITING_ON_CUSTOMER, 3, 30),
    ("Inventory count off by one after update", 2, Priority.MEDIUM, TicketStatus.WAITING_ON_CUSTOMER, 4, 20),
    ("Students see another class's timetable", 3, Priority.URGENT, TicketStatus.RESOLVED, 5, 50),
    ("Add second admin user to account", 3, Priority.LOW, TicketStatus.CLOSED, 6, 200),
    ("Appointment reminders sent twice", 4, Priority.MEDIUM, TicketStatus.REOPENED, 7, 72),
    ("Report dashboard is slow in the evenings", 4, Priority.MEDIUM, TicketStatus.OPEN, 8, 10),
]


def seed_agents(session: Session) -> list[Agent]:
    """Create missing demo agents, and reset every agent's password to DEMO_PASSWORD.

    Re-running this after changing DEMO_PASSWORD syncs existing agents too, not just new
    ones — this is a shared demo roster, so "forgot the password" means "re-run the seed".
    """
    existing = {a.email: a for a in session.scalars(select(Agent))}
    pw_hash = hash_password(DEMO_PASSWORD)
    agents = []
    for name, email, role in AGENTS:
        agent = existing.get(email)
        if agent is None:
            agent = Agent(name=name, email=email, role=role, password_hash=pw_hash)
            session.add(agent)
        else:
            agent.password_hash = pw_hash
        agents.append(agent)
    session.flush()
    return agents


def seed_customers(session: Session) -> list[Customer]:
    existing = {c.email: c for c in session.scalars(select(Customer))}
    customers = []
    for name, email, phone, company in CUSTOMERS:
        customer = existing.get(email)
        if customer is None:
            customer = Customer(name=name, email=email, phone=phone, company=company)
            session.add(customer)
        customers.append(customer)
    session.flush()
    return customers


def seed_holidays(session: Session) -> int:
    """Insert missing holidays and correct names of existing ones. Never deletes."""
    existing = {h.date: h for h in session.scalars(select(Holiday))}
    added = 0
    for day, name in HOLIDAYS:
        holiday = existing.get(day)
        if holiday is None:
            session.add(Holiday(date=day, name=name))
            added += 1
        elif holiday.name != name:
            holiday.name = name
    return added


def seed_tickets(session: Session, agents: list[Agent], customers: list[Customer]) -> int:
    existing = set(session.execute(select(Ticket.subject, Ticket.customer_id)).tuples())
    now = datetime.now(timezone.utc)
    hols = load_holidays(session)
    added = 0
    for subject, c_idx, priority, status, a_idx, hours_ago in TICKETS:
        customer = customers[c_idx]
        if (subject, customer.id) in existing:
            continue
        created = now - timedelta(hours=hours_ago)
        assignee = agents[a_idx] if a_idx is not None else None
        ticket = Ticket(
            subject=subject,
            customer_id=customer.id,
            assignee_id=assignee.id if assignee else None,
            status=status,
            priority=priority,
            created_at=created,
            last_customer_reply_at=created,
        )
        if status is TicketStatus.NEW:
            # Untriaged customer submissions (§3.1): flag + the impact they reported.
            ticket.needs_triage = True
            ticket.customer_impact = IMPACT_HINT[priority]
        if status is TicketStatus.WAITING_ON_CUSTOMER:
            ticket.paused_at = created + timedelta(hours=1)
        if status in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.REOPENED):
            ticket.resolved_at = created + timedelta(hours=hours_ago / 2)
        if status is TicketStatus.CLOSED:
            ticket.closed_at = now - timedelta(hours=1)
        if status is TicketStatus.REOPENED:
            ticket.reopen_count = 1
        ticket.first_response_due_at, ticket.resolution_due_at = compute_deadlines(ticket, hols)
        session.add(ticket)
        session.flush()

        session.add(
            Message(
                ticket_id=ticket.id,
                author_type=AuthorType.CUSTOMER,
                author_customer_id=customer.id,
                visibility=Visibility.PUBLIC,
                body=f"Hi team, {subject.lower()}. Please help.",
                created_at=created,
            )
        )
        record_event(
            session,
            ticket_id=ticket.id,
            actor_type=AuthorType.SYSTEM,
            actor_id=None,
            action=AuditAction.TICKET_CREATED,
            new={"subject": subject, "priority": priority.value, "status": status.value, "seed": True},
        )
        added += 1
    return added


def main() -> None:
    with get_sessionmaker()() as session, session.begin():
        agents = seed_agents(session)
        customers = seed_customers(session)
        holidays = seed_holidays(session)
        tickets = seed_tickets(session, agents, customers)
    print(
        f"Seed done: {len(agents)} agents, {len(customers)} customers, "
        f"+{holidays} holidays, +{tickets} tickets (demo password: {DEMO_PASSWORD})"
    )


if __name__ == "__main__":
    main()

"""Ticket state changes. See PROJECT_SUMMARY.md §3.3, §3.6, §4, §5.

Every status change goes through transition() (except the atomic claim, which sets NEW -> OPEN
in its own UPDATE); every priority change through change_priority(). All functions write their
audit events in the caller's transaction and never commit.
"""

import enum
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentRole,
    AuditAction,
    AuthorType,
    Customer,
    CustomerImpact,
    Message,
    Priority,
    Ticket,
    TicketStatus,
    Visibility,
)
from app.services.audit import Actor, record
from app.sla.policy import compute_deadlines, deadlines_for, load_holidays
from app.sla.working_hours import working_minutes_between

S = TicketStatus

ALLOWED_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    S.NEW: frozenset({S.OPEN, S.CLOSED}),
    S.OPEN: frozenset({S.WAITING_ON_CUSTOMER, S.RESOLVED}),
    S.WAITING_ON_CUSTOMER: frozenset({S.OPEN, S.RESOLVED, S.CLOSED}),
    S.RESOLVED: frozenset({S.CLOSED, S.REOPENED}),
    S.CLOSED: frozenset({S.REOPENED}),
    S.REOPENED: frozenset({S.WAITING_ON_CUSTOMER, S.RESOLVED}),
}

AUTO_CLOSE_WORKING_MINUTES = 2700  # 5 working days (§3.4)
REOPEN_WINDOW_DAYS = 7  # calendar days, not working days (§3.5)


class InvalidTransition(Exception):
    def __init__(self, from_status: TicketStatus, to_status: TicketStatus):
        self.from_status = from_status
        self.to_status = to_status
        self.allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[from_status])
        super().__init__(f"cannot move ticket from {from_status.value} to {to_status.value}")


class ReopenWindowExpired(Exception):
    """Raised by transition() targeting REOPENED when more than REOPEN_WINDOW_DAYS calendar
    days have passed since resolution/closure (§3.5). Customer replies should fall back to
    create_follow_up(); agent requests just get a clear error.
    """

    def __init__(self, ticket: Ticket, anchor_at: datetime, anchor_field: str):
        self.ticket = ticket
        self.anchor_at = anchor_at
        self.anchor_field = anchor_field  # "resolved_at" | "closed_at"
        super().__init__(
            f"ticket {ticket.id} cannot be reopened: more than {REOPEN_WINDOW_DAYS} calendar "
            f"days have passed since {anchor_field}"
        )


class TicketClosed(Exception):
    """Agent reply attempted on a CLOSED ticket (note 17, decided: block; reopen first)."""


def may_change_status(ticket: Ticket, agent: Agent, to_status: TicketStatus) -> bool:
    """Agent permission for PATCH /status (§4, notes/10).

    Assignee or ADMIN; plus any agent may close a NEW unassigned ticket (spam/duplicate).
    """
    if agent.role is AgentRole.ADMIN or ticket.assignee_id == agent.id:
        return True
    return ticket.status is S.NEW and ticket.assignee_id is None and to_status is S.CLOSED


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _deadlines(ticket: Ticket) -> dict[str, str | None]:
    return {
        "first_response_due_at": _iso(ticket.first_response_due_at),
        "resolution_due_at": _iso(ticket.resolution_due_at),
    }


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _resume_sla(
    session: Session, ticket: Ticket, actor: Actor, now: datetime, holidays: set[date]
) -> None:
    """Close the current pause: add its working minutes and shift deadlines by them (§3.3)."""
    paused = working_minutes_between(ticket.paused_at, now, holidays)
    old = {"paused_minutes": ticket.paused_minutes, **_deadlines(ticket)}
    ticket.paused_minutes = (ticket.paused_minutes or 0) + paused
    ticket.paused_at = None
    ticket.first_response_due_at, ticket.resolution_due_at = compute_deadlines(ticket, holidays)
    new = {"paused_minutes": ticket.paused_minutes, **_deadlines(ticket)}
    record(session, ticket.id, actor, AuditAction.SLA_RESUMED, "paused_minutes", old, new)


def transition(
    session: Session,
    ticket: Ticket,
    to_status: TicketStatus,
    actor: Actor,
    *,
    now: datetime | None = None,
    holidays: set[date] | None = None,
) -> None:
    """Validate and apply a status change, with SLA pause/resume. Raises InvalidTransition, or
    ReopenWindowExpired if targeting REOPENED more than REOPEN_WINDOW_DAYS after resolution.
    """
    from_status = ticket.status
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise InvalidTransition(from_status, to_status)

    now = _now(now)

    if to_status is S.REOPENED:
        anchor_field = "resolved_at" if ticket.resolved_at is not None else "closed_at"
        anchor_at = ticket.resolved_at or ticket.closed_at
        if anchor_at is None:
            # Invariant: transition() always sets resolved_at/closed_at on the way into
            # RESOLVED/CLOSED, and REOPENED is only reachable from those two statuses.
            raise ValueError(f"ticket {ticket.id} has neither resolved_at nor closed_at")
        if now - anchor_at > timedelta(days=REOPEN_WINDOW_DAYS):
            raise ReopenWindowExpired(ticket, anchor_at, anchor_field)

    if holidays is None:
        holidays = load_holidays(session)

    ticket.status = to_status
    record(
        session, ticket.id, actor, AuditAction.STATUS_CHANGED, "status",
        from_status.value, to_status.value,
    )

    if from_status is S.WAITING_ON_CUSTOMER and ticket.paused_at is not None:
        _resume_sla(session, ticket, actor, now, holidays)

    if to_status is S.WAITING_ON_CUSTOMER:
        ticket.paused_at = now
        record(session, ticket.id, actor, AuditAction.SLA_PAUSED, "paused_at", None, _iso(now))
    elif to_status is S.RESOLVED:
        ticket.resolved_at = now
    elif to_status is S.CLOSED:
        ticket.closed_at = now
    elif to_status is S.REOPENED:
        old_resolution_due = _iso(ticket.resolution_due_at)
        ticket.reopen_count = (ticket.reopen_count or 0) + 1
        ticket.resolved_at = None
        ticket.closed_at = None
        # Fresh resolution clock from the reopen moment, same priority, no carried-over pause
        # (§3.5). first_response_at/_due_at are untouched: that target was already met earlier
        # in the ticket's life and isn't meaningful again on reopen.
        _, ticket.resolution_due_at = deadlines_for(ticket.priority, now, 0, holidays)
        record(
            session, ticket.id, actor, AuditAction.REOPENED, "resolution_due_at",
            old_resolution_due, _iso(ticket.resolution_due_at),
        )


def reopen(
    session: Session,
    ticket: Ticket,
    actor: Actor,
    *,
    now: datetime | None = None,
    holidays: set[date] | None = None,
) -> None:
    """Reopen a RESOLVED/CLOSED ticket within REOPEN_WINDOW_DAYS (§3.5). Thin, readable alias
    for transition(..., TicketStatus.REOPENED, ...) — all the actual rules live there, so this
    can't be bypassed or diverge from PATCH /status targeting REOPENED directly.

    Raises ReopenWindowExpired if the window has passed.
    """
    transition(session, ticket, S.REOPENED, actor, now=now, holidays=holidays)


def change_priority(
    session: Session,
    ticket: Ticket,
    new_priority: Priority,
    actor: Actor,
    *,
    holidays: set[date] | None = None,
) -> bool:
    """Set priority; this is also the triage decision, so it always clears needs_triage (§3.1).

    A new priority recomputes deadlines from created_at (§3.6) and may breach the ticket
    immediately: audited as PRIORITY_CHANGED. Confirming the current priority on a ticket
    that needs triage only clears the flag: audited as TRIAGED. Otherwise a no-op (False).
    """
    changed = new_priority is not ticket.priority
    if not changed and not ticket.needs_triage:
        return False

    def snapshot() -> dict:
        return {
            "priority": ticket.priority.value,
            "needs_triage": ticket.needs_triage,
            **_deadlines(ticket),
        }

    old = snapshot()
    ticket.needs_triage = False
    if changed:
        if holidays is None:
            holidays = load_holidays(session)
        ticket.priority = new_priority
        ticket.first_response_due_at, ticket.resolution_due_at = compute_deadlines(
            ticket, holidays
        )
    action, field = (
        (AuditAction.PRIORITY_CHANGED, "priority") if changed else (AuditAction.TRIAGED, "needs_triage")
    )
    record(session, ticket.id, actor, action, field, old, snapshot())
    return True


# --- INC-0291: atomic claim ----------------------------------------------------------------


class ClaimOutcome(enum.Enum):
    CLAIMED = "claimed"
    ALREADY_MINE = "already_mine"
    TAKEN = "taken"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class ClaimResult:
    outcome: ClaimOutcome
    assignee_name: str | None = None


# One statement: only succeeds while assignee_id IS NULL. A concurrent claimer blocks on the
# row lock, then re-checks the WHERE against the committed row and matches 0 rows.
_CLAIM_SQL = text(
    """
    WITH before AS (SELECT id, status FROM tickets WHERE id = :id)
    UPDATE tickets AS t
       SET assignee_id = :agent_id,
           status = CASE WHEN t.status = 'NEW' THEN 'OPEN'::ticket_status ELSE t.status END,
           updated_at = now()
      FROM before
     WHERE t.id = before.id AND t.assignee_id IS NULL
    RETURNING before.status::text AS old_status, t.status::text AS new_status
    """
)


def claim(session: Session, ticket_id: int, agent: Agent) -> ClaimResult:
    row = session.execute(_CLAIM_SQL, {"id": ticket_id, "agent_id": agent.id}).one_or_none()
    if row is not None:
        actor = Actor.agent(agent.id)
        record(session, ticket_id, actor, AuditAction.CLAIMED, "assignee_id", None, agent.id)
        if row.old_status != row.new_status:
            record(
                session, ticket_id, actor, AuditAction.STATUS_CHANGED, "status",
                row.old_status, row.new_status,
            )
        _refresh_if_loaded(session, ticket_id)
        return ClaimResult(ClaimOutcome.CLAIMED, agent.name)

    ticket = session.get(Ticket, ticket_id, populate_existing=True)
    if ticket is None:
        return ClaimResult(ClaimOutcome.NOT_FOUND)
    if ticket.assignee_id == agent.id:
        return ClaimResult(ClaimOutcome.ALREADY_MINE, agent.name)
    return ClaimResult(ClaimOutcome.TAKEN, ticket.assignee.name if ticket.assignee else None)


def _refresh_if_loaded(session: Session, ticket_id: int) -> None:
    """The raw UPDATE bypassed the ORM; reload a cached Ticket so callers see new values."""
    session.get(Ticket, ticket_id, populate_existing=True)


# --- Messages ------------------------------------------------------------------------------


class NotAssignee(Exception):
    pass


def add_reply(
    session: Session, ticket: Ticket, agent: Agent, body: str, *, now: datetime | None = None
) -> Message:
    """PUBLIC reply. Assignee only (INC-0291). The first one sets first_response_at (§3.1).

    Blocked on CLOSED tickets (note 17, decided): reopen first. RESOLVED is still allowed —
    only CLOSED is truly terminal. Internal notes (add_note) are never blocked.
    """
    if ticket.assignee_id != agent.id:
        raise NotAssignee()
    if ticket.status is S.CLOSED:
        raise TicketClosed()
    now = _now(now)
    message = Message(
        ticket_id=ticket.id,
        author_type=AuthorType.AGENT,
        author_agent_id=agent.id,
        visibility=Visibility.PUBLIC,
        body=body,
        created_at=now,
    )
    session.add(message)
    if ticket.first_response_at is None:
        ticket.first_response_at = now
    session.flush()
    record(
        session, ticket.id, Actor.agent(agent.id), AuditAction.REPLY_SENT, "message_id",
        None, message.id,
    )
    return message


def add_note(
    session: Session, ticket: Ticket, agent: Agent, body: str, *, now: datetime | None = None
) -> Message:
    """INTERNAL note. Any agent. Never counts as a first response, never reaches a customer."""
    message = Message(
        ticket_id=ticket.id,
        author_type=AuthorType.AGENT,
        author_agent_id=agent.id,
        visibility=Visibility.INTERNAL,
        body=body,
        created_at=_now(now),
    )
    session.add(message)
    session.flush()
    record(
        session, ticket.id, Actor.agent(agent.id), AuditAction.NOTE_ADDED, "message_id",
        None, message.id,
    )
    return message


# --- Auto-close (§3.4) ----------------------------------------------------------------------


def auto_close_overdue_tickets(
    session: Session, *, now: datetime | None = None, holidays: set[date] | None = None
) -> list[Ticket]:
    """Close WAITING_ON_CUSTOMER/RESOLVED tickets with no customer reply for 5 working days.

    The clock counts from paused_at (waiting) or resolved_at (resolved). Actor is SYSTEM.
    Idempotent: a closed ticket's status no longer matches the query, so re-running the job
    finds nothing left to do for it.
    """
    now = _now(now)
    if holidays is None:
        holidays = load_holidays(session)
    actor = Actor.system()

    candidates = session.scalars(
        select(Ticket).where(
            Ticket.status.in_((TicketStatus.WAITING_ON_CUSTOMER, TicketStatus.RESOLVED))
        )
    ).all()

    closed = []
    for ticket in candidates:
        anchor = (
            ticket.paused_at if ticket.status is TicketStatus.WAITING_ON_CUSTOMER
            else ticket.resolved_at
        )
        if anchor is None:
            continue  # shouldn't happen given the invariants, but don't let one bad row crash the job
        elapsed = working_minutes_between(anchor, now, holidays)
        if elapsed < AUTO_CLOSE_WORKING_MINUTES:
            continue
        transition(session, ticket, S.CLOSED, actor, now=now, holidays=holidays)
        record(
            session, ticket.id, actor, AuditAction.AUTO_CLOSED, "elapsed_working_minutes",
            None, elapsed,
        )
        closed.append(ticket)
    return closed


# --- Customer side -------------------------------------------------------------------------


def create_customer_ticket(
    session: Session,
    *,
    name: str,
    email: str,
    subject: str,
    body: str,
    phone: str | None = None,
    company: str | None = None,
    customer_impact: CustomerImpact | None = None,
    now: datetime | None = None,
) -> Ticket:
    """A ticket submitted by a customer. Finds or creates the customer by email.

    Customers don't choose priority: it starts at MEDIUM with needs_triage=True until an agent
    sets it; their stated impact is only a hint (§3.1, notes/15).
    """
    priority = Priority.MEDIUM
    now = _now(now)
    email = email.strip().lower()
    customer = session.query(Customer).filter(Customer.email == email).one_or_none()
    if customer is None:
        customer = Customer(name=name, email=email, phone=phone, company=company)
        session.add(customer)
        session.flush()

    ticket = Ticket(
        subject=subject,
        customer_id=customer.id,
        status=TicketStatus.NEW,
        priority=priority,
        created_at=now,
        last_customer_reply_at=now,
        paused_minutes=0,
        reopen_count=0,
        needs_triage=True,
        customer_impact=customer_impact,
    )
    ticket.first_response_due_at, ticket.resolution_due_at = compute_deadlines(
        ticket, load_holidays(session)
    )
    session.add(ticket)
    session.flush()
    session.add(
        Message(
            ticket_id=ticket.id,
            author_type=AuthorType.CUSTOMER,
            author_customer_id=customer.id,
            visibility=Visibility.PUBLIC,
            body=body,
            created_at=now,
        )
    )
    record(
        session, ticket.id, Actor.customer(customer.id), AuditAction.TICKET_CREATED, None, None,
        {
            "subject": subject,
            "priority": priority.value,
            "status": TicketStatus.NEW.value,
            "needs_triage": True,
            "customer_impact": customer_impact.value if customer_impact else None,
        },
    )
    session.flush()
    return ticket


def create_follow_up(
    session: Session,
    old_ticket: Ticket,
    body: str,
    *,
    now: datetime | None = None,
    holidays: set[date] | None = None,
) -> tuple[Ticket, Message]:
    """A customer reply arrives more than REOPEN_WINDOW_DAYS after resolution/closure: open a
    new ticket linked to the old one instead of reopening it (§3.5).

    Same priority as the parent; flagged needs_triage since it's effectively a fresh report an
    agent should re-confirm. The customer's message lands on the NEW ticket only.
    """
    now = _now(now)
    if holidays is None:
        holidays = load_holidays(session)
    actor = Actor.customer(old_ticket.customer_id)

    new_ticket = Ticket(
        subject=f"Follow-up: {old_ticket.subject}",
        customer_id=old_ticket.customer_id,
        status=TicketStatus.NEW,
        priority=old_ticket.priority,
        created_at=now,
        last_customer_reply_at=now,
        paused_minutes=0,
        reopen_count=0,
        needs_triage=True,
        customer_impact=old_ticket.customer_impact,
        parent_ticket_id=old_ticket.id,
    )
    new_ticket.first_response_due_at, new_ticket.resolution_due_at = compute_deadlines(
        new_ticket, holidays
    )
    session.add(new_ticket)
    session.flush()

    message = Message(
        ticket_id=new_ticket.id,
        author_type=AuthorType.CUSTOMER,
        author_customer_id=old_ticket.customer_id,
        visibility=Visibility.PUBLIC,
        body=body,
        created_at=now,
    )
    session.add(message)
    session.flush()

    record(
        session, old_ticket.id, actor, AuditAction.FOLLOW_UP_CREATED, "parent_ticket_id",
        None, new_ticket.id,
    )
    record(
        session, new_ticket.id, actor, AuditAction.TICKET_CREATED, None, None,
        {
            "subject": new_ticket.subject,
            "priority": new_ticket.priority.value,
            "status": TicketStatus.NEW.value,
            "needs_triage": True,
            "parent_ticket_id": old_ticket.id,
        },
    )
    return new_ticket, message


def add_customer_reply(
    session: Session, ticket: Ticket, body: str, *, now: datetime | None = None
) -> tuple[Ticket, Message]:
    """Customer reply. Resumes the SLA clock if waiting; reopens within the 7-day window if
    resolved/closed, or creates a linked follow-up ticket after the window (§3.3, §3.5).

    Returns (ticket_the_message_landed_on, message) — this differs from the input `ticket`
    only when a follow-up was created, so callers must use the returned ticket, not the input.
    """
    now = _now(now)
    holidays = load_holidays(session)
    actor = Actor.customer(ticket.customer_id)

    if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        try:
            transition(session, ticket, TicketStatus.REOPENED, actor, now=now, holidays=holidays)
        except ReopenWindowExpired:
            return create_follow_up(session, ticket, body, now=now, holidays=holidays)

    message = Message(
        ticket_id=ticket.id,
        author_type=AuthorType.CUSTOMER,
        author_customer_id=ticket.customer_id,
        visibility=Visibility.PUBLIC,
        body=body,
        created_at=now,
    )
    session.add(message)
    ticket.last_customer_reply_at = now
    session.flush()
    record(session, ticket.id, actor, AuditAction.CUSTOMER_REPLIED, "message_id", None, message.id)
    if ticket.status is TicketStatus.WAITING_ON_CUSTOMER:
        transition(session, ticket, TicketStatus.OPEN, actor, now=now, holidays=holidays)
    return ticket, message

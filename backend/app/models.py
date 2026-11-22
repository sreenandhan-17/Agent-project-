"""Database models. See PROJECT_SUMMARY.md §6."""

import enum
import secrets
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AgentRole(str, enum.Enum):
    AGENT = "AGENT"
    ADMIN = "ADMIN"


class TicketStatus(str, enum.Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    WAITING_ON_CUSTOMER = "WAITING_ON_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class Priority(str, enum.Enum):
    URGENT = "URGENT"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AuthorType(str, enum.Enum):
    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"


class Visibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class AuditAction(str, enum.Enum):
    TICKET_CREATED = "TICKET_CREATED"
    CLAIMED = "CLAIMED"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    REPLY_SENT = "REPLY_SENT"
    NOTE_ADDED = "NOTE_ADDED"
    CUSTOMER_REPLIED = "CUSTOMER_REPLIED"
    SLA_PAUSED = "SLA_PAUSED"
    SLA_RESUMED = "SLA_RESUMED"
    AUTO_CLOSED = "AUTO_CLOSED"
    REOPENED = "REOPENED"
    FOLLOW_UP_CREATED = "FOLLOW_UP_CREATED"


def _pg_enum(py_enum: type[enum.Enum], name: str) -> Enum:
    return Enum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


# Actor types in the audit log are the same set as message authors.
ActorType = AuthorType



def new_public_token() -> str:
    return secrets.token_urlsafe(24)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[AgentRole] = mapped_column(_pg_enum(AgentRole, "agent_role"), default=AgentRole.AGENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    company: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_resolution_due_at", "resolution_due_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'FD-' || nextval('ticket_number_seq')"),
    )
    subject: Mapped[str] = mapped_column(String(200))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[TicketStatus] = mapped_column(
        _pg_enum(TicketStatus, "ticket_status"), default=TicketStatus.NEW
    )
    priority: Mapped[Priority] = mapped_column(_pg_enum(Priority, "ticket_priority"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # SLA. Due dates are derived by the working-hours calculator (steps 2-3) and stored for filtering.
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    last_customer_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    parent_ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    public_token: Mapped[str] = mapped_column(String(64), unique=True, default=new_public_token)

    customer: Mapped[Customer] = relationship()
    assignee: Mapped[Agent | None] = relationship()
    messages: Mapped[list["Message"]] = relationship(back_populates="ticket", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_ticket_id", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    author_type: Mapped[AuthorType] = mapped_column(_pg_enum(AuthorType, "author_type"))
    author_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    author_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    visibility: Mapped[Visibility] = mapped_column(_pg_enum(Visibility, "message_visibility"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="messages")


class AuditEvent(Base):
    """Append-only. A DB trigger blocks UPDATE/DELETE/TRUNCATE and forces created_at to server time."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_ticket_id", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    actor_type: Mapped[AuthorType] = mapped_column(_pg_enum(AuthorType, "author_type"))
    actor_id: Mapped[int | None] = mapped_column(Integer)  # agent or customer id; NULL for SYSTEM
    action: Mapped[AuditAction] = mapped_column(_pg_enum(AuditAction, "audit_action"))
    field: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Holiday(Base):
    __tablename__ = "holidays"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))

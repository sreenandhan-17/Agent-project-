from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import ActorType, AuditAction, AuditEvent


@dataclass(frozen=True)
class Actor:
    """Who performed an action. id is NULL for SYSTEM."""

    type: ActorType
    id: int | None = None

    @classmethod
    def agent(cls, agent_id: int) -> "Actor":
        return cls(ActorType.AGENT, agent_id)

    @classmethod
    def customer(cls, customer_id: int) -> "Actor":
        return cls(ActorType.CUSTOMER, customer_id)

    @classmethod
    def system(cls) -> "Actor":
        return cls(ActorType.SYSTEM, None)


def record_event(
    session: Session,
    ticket_id: int | None,
    actor_type: ActorType,
    actor_id: int | None,
    action: AuditAction,
    field: str | None = None,
    old: Any = None,
    new: Any = None,
) -> AuditEvent:
    """Add an audit event to the caller's transaction. Never commits.

    created_at is not accepted: the DB sets it to server time.
    """
    event = AuditEvent(
        ticket_id=ticket_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        field=field,
        old_value=old,
        new_value=new,
    )
    session.add(event)
    return event


def record(
    session: Session,
    ticket_id: int | None,
    actor: Actor,
    action: AuditAction,
    field: str | None = None,
    old: Any = None,
    new: Any = None,
) -> AuditEvent:
    """record_event() taking an Actor."""
    return record_event(session, ticket_id, actor.type, actor.id, action, field, old, new)

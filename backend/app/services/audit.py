from typing import Any

from sqlalchemy.orm import Session

from app.models import ActorType, AuditAction, AuditEvent


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

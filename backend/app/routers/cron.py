"""Scheduled jobs, triggered by Vercel Cron. See PROJECT_SUMMARY.md §3.4.

Vercel sends `Authorization: Bearer $CRON_SECRET` automatically when the env var is named
CRON_SECRET, so this also doubles as a manual trigger for anyone who holds the secret.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.services.tickets import auto_close_overdue_tickets

router = APIRouter(prefix="/api/cron", tags=["cron"])


def require_cron_secret(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {get_settings().cron_secret}"
    # hmac.compare_digest: a plain `!=` leaks the secret's length/prefix via response timing.
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing cron secret")


@router.get("/auto-close", dependencies=[Depends(require_cron_secret)])
def auto_close(session: Session = Depends(get_session)) -> dict:
    """Close WAITING_ON_CUSTOMER/RESOLVED tickets with no customer reply for 5 working days,
    actor=system (§3.4). Idempotent: safe to run more than once or more often than scheduled.
    """
    closed = auto_close_overdue_tickets(session)
    session.commit()
    return {"status": "ok", "closed": len(closed), "ticket_ids": [t.id for t in closed]}

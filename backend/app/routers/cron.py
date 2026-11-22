"""Scheduled jobs, triggered by Vercel Cron. See PROJECT_SUMMARY.md §3.4.

Vercel sends `Authorization: Bearer $CRON_SECRET` automatically when the env var is named
CRON_SECRET, so this also doubles as a manual trigger for anyone who holds the secret.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import get_settings

router = APIRouter(prefix="/api/cron", tags=["cron"])


def require_cron_secret(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {get_settings().cron_secret}"
    # hmac.compare_digest: a plain `!=` leaks the secret's length/prefix via response timing.
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing cron secret")


@router.get("/auto-close", dependencies=[Depends(require_cron_secret)])
def auto_close() -> dict:
    """STUB (build step 7). Will close WAITING_ON_CUSTOMER/RESOLVED tickets after 5 working
    days of no customer reply, with actor=system (§3.4). For now this only confirms the cron
    is wired up correctly end-to-end (auth, schedule, deploy) and does nothing to the data.
    """
    return {"status": "ok", "closed": 0, "note": "auto-close logic not yet implemented (step 7)"}

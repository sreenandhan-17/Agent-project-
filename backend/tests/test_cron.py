"""Step 6: the cron endpoint is protected by CRON_SECRET (stub logic; real work is step 7)."""

import pytest

from app.config import get_settings


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-secret"},
        {"Authorization": "wrong-scheme"},
        {"Authorization": "Bearer " + get_settings().cron_secret[:-1]},  # one char short
    ],
)
def test_wrong_or_missing_secret_rejected(api, headers):
    r = api.get("/api/cron/auto-close", headers=headers)
    assert r.status_code == 401


def test_correct_secret_accepted(api):
    headers = {"Authorization": f"Bearer {get_settings().cron_secret}"}
    r = api.get("/api/cron/auto-close", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_endpoint_does_not_require_agent_login(api):
    """Vercel Cron can't send an agent JWT; the cron secret alone must be enough."""
    r = api.get(
        "/api/cron/auto-close", headers={"Authorization": f"Bearer {get_settings().cron_secret}"}
    )
    assert r.status_code != 401

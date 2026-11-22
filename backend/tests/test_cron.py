"""The cron endpoint is protected by CRON_SECRET. Real auto-close logic is tested in
tests/test_auto_close.py; this file only covers the auth gate and response shape.
"""

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
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["closed"], int)
    assert isinstance(body["ticket_ids"], list)


def test_endpoint_does_not_require_agent_login(api):
    """Vercel Cron can't send an agent JWT; the cron secret alone must be enough."""
    r = api.get(
        "/api/cron/auto-close", headers={"Authorization": f"Bearer {get_settings().cron_secret}"}
    )
    assert r.status_code != 401

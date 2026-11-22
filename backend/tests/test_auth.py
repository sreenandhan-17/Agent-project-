"""Issue 08: JWT login replaces the temporary X-Agent-Id header."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth import ALGORITHM, TOKEN_TTL, create_access_token, decode_access_token
from tests.conftest import TEST_PASSWORD, auth_headers


@pytest.fixture
def login_agent(make_agent):
    return make_agent(password=TEST_PASSWORD)


def login(api, email, password):
    return api.post("/api/auth/login", json={"email": email, "password": password})


def test_login_returns_token_that_works_on_me(api, login_agent):
    r = login(api, login_agent.email, TEST_PASSWORD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["agent"]["id"] == login_agent.id
    assert "password_hash" not in body["agent"]

    me = api.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == login_agent.email


def test_token_claims(login_agent):
    token = create_access_token(login_agent.id)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["sub"] == str(login_agent.id)
    assert payload["exp"] - payload["iat"] == TOKEN_TTL.total_seconds() == 12 * 3600
    assert jwt.get_unverified_header(token)["alg"] == ALGORITHM == "HS256"


def test_login_email_is_case_insensitive(api, login_agent):
    assert login(api, login_agent.email.upper(), TEST_PASSWORD).status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(api, login_agent):
    wrong = login(api, login_agent.email, "nope")
    unknown = login(api, "nobody@test.example", TEST_PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_inactive_agent_cannot_log_in_or_use_old_token(api, session, login_agent):
    headers = auth_headers(login_agent)
    login_agent.is_active = False
    session.flush()
    assert login(api, login_agent.email, TEST_PASSWORD).status_code == 401
    assert api.get("/api/auth/me", headers=headers).status_code == 401


def test_expired_token_rejected(api, agent):
    old = create_access_token(agent.id, now=datetime.now(timezone.utc) - TOKEN_TTL - timedelta(1))
    r = api.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"})
    assert r.status_code == 401


def test_token_signed_with_other_secret_rejected(api, agent):
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {"sub": str(agent.id), "iat": now, "exp": now + TOKEN_TTL}, "attacker-secret", ALGORITHM
    )
    r = api.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_unsigned_alg_none_token_rejected(agent):
    forged = jwt.encode({"sub": str(agent.id), "exp": 9999999999}, None, algorithm="none")
    with pytest.raises(Exception):
        decode_access_token(forged)


@pytest.mark.parametrize("hdrs", [{}, {"Authorization": "Bearer garbage"}])
def test_me_requires_valid_token(api, hdrs):
    r = api.get("/api/auth/me", headers=hdrs)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_unknown_agent_id_in_valid_token_rejected(api):
    r = api.get("/api/auth/me", headers={"Authorization": f"Bearer {create_access_token(999999)}"})
    assert r.status_code == 401

"""Issue 13: no hard-coded secrets outside ENV=dev; secrets must be >= 32 chars."""

import pytest
from pydantic import ValidationError

from app.config import MIN_SECRET_LENGTH, Settings

STRONG = "x" * MIN_SECRET_LENGTH
DB = "postgresql://u:p@localhost/db"


@pytest.fixture
def load(monkeypatch):
    """Build Settings from exactly the given env vars: no .env file, no inherited values."""

    def _load(**env: str) -> Settings:
        for var in (
            "ENV", "DATABASE_URL", "TEST_DATABASE_URL", "JWT_SECRET", "CRON_SECRET",
            "PUBLIC_BASE_URL", "VERCEL_PROJECT_PRODUCTION_URL",
        ):
            monkeypatch.delenv(var, raising=False)
        for var, value in env.items():
            monkeypatch.setenv(var, value)
        return Settings(_env_file=None)

    return _load


def test_production_without_jwt_secret_fails(load):
    with pytest.raises(ValidationError, match="JWT_SECRET is not set"):
        load(ENV="production", DATABASE_URL=DB, CRON_SECRET=STRONG)


def test_unset_env_counts_as_production(load):
    with pytest.raises(ValidationError, match="JWT_SECRET is not set"):
        load(DATABASE_URL=DB, CRON_SECRET=STRONG)


def test_production_without_cron_secret_fails(load):
    with pytest.raises(ValidationError, match="CRON_SECRET is not set"):
        load(ENV="production", DATABASE_URL=DB, JWT_SECRET=STRONG)


def test_error_names_both_missing_secrets_and_how_to_fix(load):
    with pytest.raises(ValidationError) as err:
        load(ENV="production", DATABASE_URL=DB)
    message = str(err.value)
    assert "JWT_SECRET is not set" in message
    assert "CRON_SECRET is not set" in message
    assert "secrets.token_urlsafe" in message


def test_error_does_not_echo_secrets_or_db_password(load):
    with pytest.raises(ValidationError) as err:
        load(ENV="production", DATABASE_URL="postgresql://u:hunter2-db-pass@h/db",
             CRON_SECRET="c" * 20 + "TOPSECRET")
    message = str(err.value)
    assert "hunter2-db-pass" not in message
    assert "TOPSECRET" not in message


@pytest.mark.parametrize("env", ["production", "dev"])
def test_short_secret_rejected_even_in_dev(load, env):
    with pytest.raises(ValidationError, match="JWT_SECRET must be at least 32 characters"):
        load(ENV=env, DATABASE_URL=DB, JWT_SECRET="x" * 31, CRON_SECRET=STRONG)


def test_production_with_strong_secrets_loads(load):
    s = load(
        ENV="production", DATABASE_URL=DB, JWT_SECRET=STRONG, CRON_SECRET=STRONG + "c",
        PUBLIC_BASE_URL="https://support.arvo.example",
    )
    assert not s.is_dev
    assert (s.jwt_secret, s.cron_secret) == (STRONG, STRONG + "c")


@pytest.mark.parametrize("env", ["dev", "DEV", " Dev "])
def test_dev_falls_back_to_long_dev_secrets(load, env):
    s = load(ENV=env, DATABASE_URL=DB)
    assert s.is_dev
    assert len(s.jwt_secret) >= MIN_SECRET_LENGTH
    assert len(s.cron_secret) >= MIN_SECRET_LENGTH
    assert s.jwt_secret != s.cron_secret


def test_dev_uses_provided_secret_over_default(load):
    assert load(ENV="dev", DATABASE_URL=DB, JWT_SECRET=STRONG).jwt_secret == STRONG


# --- PUBLIC_BASE_URL (notes/18) ----------------------------------------------------------

PROD = {"ENV": "production", "DATABASE_URL": DB, "JWT_SECRET": STRONG, "CRON_SECRET": STRONG}


def test_public_base_url_required_in_production(load):
    with pytest.raises(ValidationError, match="PUBLIC_BASE_URL is not set"):
        load(**PROD)


def test_public_base_url_explicit_and_trailing_slash_stripped(load):
    s = load(**PROD, PUBLIC_BASE_URL="https://support.arvo.example/")
    assert s.public_base_url == "https://support.arvo.example"


def test_public_base_url_falls_back_to_vercel_production_domain(load):
    s = load(**PROD, VERCEL_PROJECT_PRODUCTION_URL="frontdesk-arvo.vercel.app")
    assert s.public_base_url == "https://frontdesk-arvo.vercel.app"


def test_explicit_public_base_url_beats_vercel_domain(load):
    s = load(**PROD, PUBLIC_BASE_URL="https://support.arvo.example",
             VERCEL_PROJECT_PRODUCTION_URL="frontdesk-arvo.vercel.app")
    assert s.public_base_url == "https://support.arvo.example"


def test_public_base_url_dev_default_is_vite(load):
    assert load(ENV="dev", DATABASE_URL=DB).public_base_url == "http://localhost:5173"


def test_public_base_url_must_be_http(load):
    with pytest.raises(ValidationError, match="must start with https://"):
        load(**PROD, PUBLIC_BASE_URL="support.arvo.example")

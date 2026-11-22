"""Step 6: normalize_db_url() picks the psycopg3 driver and enforces sslmode on remote hosts."""

import pytest

from app.config import normalize_db_url


@pytest.mark.parametrize("prefix", ["postgres://", "postgresql://"])
def test_driver_is_rewritten_to_psycopg3(prefix):
    assert normalize_db_url(f"{prefix}user:pw@localhost/db").startswith("postgresql+psycopg://")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_local_hosts_are_left_without_sslmode(host):
    url = normalize_db_url(f"postgresql://u:p@{host}:5432/db")
    assert "sslmode" not in url


def test_remote_host_gets_sslmode_require():
    url = normalize_db_url("postgresql://u:p@ep-xyz-pooler.ap-southeast-1.aws.neon.tech/db")
    assert "sslmode=require" in url


def test_explicit_sslmode_is_not_overridden():
    url = normalize_db_url("postgresql://u:p@some-host.example.com/db?sslmode=verify-full")
    assert "sslmode=verify-full" in url
    assert url.count("sslmode=") == 1


def test_other_query_params_are_preserved_alongside_sslmode():
    url = normalize_db_url("postgresql://u:p@some-host.example.com/db?application_name=frontdesk")
    assert "application_name=frontdesk" in url
    assert "sslmode=require" in url

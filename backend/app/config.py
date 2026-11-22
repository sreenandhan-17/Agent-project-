from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

MIN_SECRET_LENGTH = 32
DEV_PUBLIC_BASE_URL = "http://localhost:5173"  # Vite dev server

# Used ONLY when ENV=dev and the variable is unset. Public on purpose: never valid in production.
_DEV_SECRETS = {
    "jwt_secret": "dev-only-jwt-secret-do-not-use-in-production-000000",
    "cron_secret": "dev-only-cron-secret-do-not-use-in-production-00000",
}


def normalize_db_url(url: str) -> str:
    """Neon hands out postgresql:// URLs; SQLAlchemy needs the psycopg 3 driver named."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    # hide_input_in_errors: a config error must not print secrets or the DB password into logs.
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", extra="ignore", hide_input_in_errors=True
    )

    # Anything other than "dev" (including unset) is treated as production.
    env: str = "production"
    database_url: str
    test_database_url: str | None = None
    # No defaults: required unless ENV=dev (notes/13).
    jwt_secret: str | None = None
    cron_secret: str | None = None
    # Where customers open their ticket (/t/{token}) from emails (notes/18). Resolved in
    # _require_public_base_url: PUBLIC_BASE_URL, else Vercel's production domain, else the
    # Vite dev server when ENV=dev.
    public_base_url: str | None = None
    vercel_project_production_url: str | None = None  # set by Vercel, hostname only

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _normalize(cls, v: str | None) -> str | None:
        return normalize_db_url(v) if v else None

    @field_validator("env")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @model_validator(mode="after")
    def _require_strong_secrets(self) -> "Settings":
        problems = []
        for field, var in (("jwt_secret", "JWT_SECRET"), ("cron_secret", "CRON_SECRET")):
            value = getattr(self, field)
            if not value and self.is_dev:
                value = _DEV_SECRETS[field]
                setattr(self, field, value)
            if not value:
                problems.append(f"{var} is not set (required unless ENV=dev)")
            elif len(value) < MIN_SECRET_LENGTH:
                problems.append(f"{var} must be at least {MIN_SECRET_LENGTH} characters")
        if problems:
            raise ValueError(
                "Invalid configuration: " + "; ".join(problems) + ". Generate a secret with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return self

    @model_validator(mode="after")
    def _require_public_base_url(self) -> "Settings":
        url = self.public_base_url
        if not url and self.vercel_project_production_url:
            url = f"https://{self.vercel_project_production_url}"
        if not url and self.is_dev:
            url = DEV_PUBLIC_BASE_URL
        if not url:
            raise ValueError(
                "Invalid configuration: PUBLIC_BASE_URL is not set (e.g. https://frontdesk.example"
                ".com; required unless ENV=dev or running on Vercel)"
            )
        if not url.startswith(("https://", "http://")):
            raise ValueError("Invalid configuration: PUBLIC_BASE_URL must start with https://")
        self.public_base_url = url.rstrip("/")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

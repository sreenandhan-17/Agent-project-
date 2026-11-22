from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


def normalize_db_url(url: str) -> str:
    """Neon hands out postgresql:// URLs; SQLAlchemy needs the psycopg 3 driver named."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None
    jwt_secret: str = "dev-only-secret"
    cron_secret: str = "dev-only-cron-secret"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _normalize(cls, v: str | None) -> str | None:
        return normalize_db_url(v) if v else None


@lru_cache
def get_settings() -> Settings:
    return Settings()

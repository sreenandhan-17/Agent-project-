"""Password hashing and JWT access tokens for agents."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=12)

# Compared against when the email is unknown, so login takes the same time either way.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


class InvalidToken(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), (password_hash or _DUMMY_HASH).encode())
    except ValueError:  # malformed stored hash
        return False


def create_access_token(agent_id: int, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    payload = {"sub": str(agent_id), "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """Agent id from a valid, unexpired token. Raises InvalidToken."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidToken(str(e)) from e

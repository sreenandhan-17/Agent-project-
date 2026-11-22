from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import InvalidToken, decode_access_token
from app.db import get_session
from app.models import Agent

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_agent(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> Agent:
    """The agent identified by `Authorization: Bearer <jwt>`. 401 otherwise."""
    if credentials is None:
        raise _unauthorized("not authenticated")
    try:
        agent_id = decode_access_token(credentials.credentials)
    except InvalidToken:
        raise _unauthorized("invalid or expired token")
    agent = session.get(Agent, agent_id)
    if agent is None or not agent.is_active:
        raise _unauthorized("unknown or inactive agent")
    return agent

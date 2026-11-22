from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Agent


def get_current_agent(
    x_agent_id: int | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Agent:
    """TEMPORARY: trusts an X-Agent-Id header. Replaced by JWT login (notes/08)."""
    if x_agent_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Agent-Id header required")
    agent = session.get(Agent, x_agent_id)
    if agent is None or not agent.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or inactive agent")
    return agent

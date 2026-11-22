from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_agent
from app.models import Agent
from app.routers.auth import AgentOut

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(get_current_agent)])


@router.get("", response_model=list[AgentOut])
def list_agents(session: Session = Depends(get_session)):
    """Active agents, for assignee names and filters in the UI."""
    return session.scalars(select(Agent).where(Agent.is_active).order_by(Agent.name)).all()

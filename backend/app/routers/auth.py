from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, verify_password
from app.db import get_session
from app.deps import get_current_agent
from app.models import Agent, AgentRole

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: AgentRole


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    agent: AgentOut


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    agent = session.scalars(
        select(Agent).where(func.lower(Agent.email) == body.email.strip().lower())
    ).one_or_none()
    # Always run bcrypt (dummy hash for unknown emails) and give one message for both failures.
    ok = verify_password(body.password, agent.password_hash if agent else None)
    if agent is None or not ok or not agent.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    return LoginResponse(access_token=create_access_token(agent.id), agent=agent)


@router.get("/me", response_model=AgentOut)
def me(agent: Agent = Depends(get_current_agent)):
    return agent

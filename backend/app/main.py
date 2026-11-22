from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_session
from app.routers import auth, public, tickets

app = FastAPI(title="Frontdesk API")
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(public.router)


@app.get("/api/health")
def health(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": False})
    return {"status": "ok", "db": True}

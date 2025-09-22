from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import models
from .config import DEBUG, SECRET_KEY
from .db import get_db, init_db
from .routers import armories, armies, auth, export, rosters
from .security import get_current_user
from .services import costs

logger = logging.getLogger(__name__)

app = FastAPI(debug=DEBUG)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    logger.info("Application started")


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user(optional=True)),
):
    armies = db.execute(select(models.Army).order_by(models.Army.created_at.desc()).limit(5)).scalars().all()
    rosters_list = (
        db.execute(select(models.Roster).order_by(models.Roster.created_at.desc()).limit(5)).scalars().all()
    )
    for roster in rosters_list:
        costs.update_cached_costs(roster.roster_units)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": current_user,
            "armies": armies,
            "rosters": rosters_list,
        },
    )


app.include_router(auth.router)
app.include_router(armories.router)
app.include_router(armies.router)
app.include_router(rosters.router)
app.include_router(export.router)

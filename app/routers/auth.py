from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if current_user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("auth_login.html", {"request": request, "error": None})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.execute(select(models.User).where(models.User.username == username)).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "auth_login.html",
            {"request": request, "error": "Nieprawidłowy login lub hasło"},
            status_code=400,
        )
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if current_user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("auth_register.html", {"request": request, "error": None})


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.execute(select(models.User).where(models.User.username == username)).scalar_one_or_none()
    if existing:
        return templates.TemplateResponse(
            "auth_register.html",
            {"request": request, "error": "Użytkownik o takiej nazwie już istnieje"},
            status_code=400,
        )
    user = models.User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse(url="/", status_code=303)

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import models
from ..security import get_current_user
from ..services import updater

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")
current_user_dep = get_current_user()


def _require_admin(user: models.User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Brak uprawnień")


def _status_messages(status_key: str | None, detail: str | None) -> tuple[str | None, str | None]:
    if status_key == "update-ok":
        return detail or "Repozytorium zostało zaktualizowane.", None
    if status_key == "update-error":
        return None, detail or "Aktualizacja repozytorium nie powiodła się."
    return None, None


@router.get("", response_class=HTMLResponse, name="admin_dashboard")
def admin_dashboard(
    request: Request, current_user: models.User = Depends(current_user_dep)
):
    _require_admin(current_user)

    status_key = request.query_params.get("status")
    detail = request.query_params.get("detail")
    message, error = _status_messages(status_key, detail)

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "user": current_user,
            "message": message,
            "error": error,
        },
    )


@router.post("/update")
def trigger_update(
    request: Request, current_user: models.User = Depends(current_user_dep)
) -> RedirectResponse:
    _require_admin(current_user)
    logger.info(
        "Aktualizacja repozytorium uruchomiona przez użytkownika %s", current_user.username
    )
    try:
        message = updater.sync_repository()
    except updater.UpdateError as exc:
        logger.error(
            "Aktualizacja repozytorium nie powiodła się dla użytkownika %s: %s",
            current_user.username,
            exc,
        )
        redirect_url = f"/admin?status=update-error&detail={quote_plus(str(exc))}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    logger.info(
        "Aktualizacja repozytorium zakończona powodzeniem dla użytkownika %s",
        current_user.username,
    )
    redirect_url = f"/admin?status=update-ok&detail={quote_plus(message)}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

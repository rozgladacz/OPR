from __future__ import annotations

import logging
import secrets
from uuid import uuid4
from urllib.parse import quote_plus

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .. import config, models
from ..security import get_current_user
from ..services import update_service, updater

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")
current_user_dep = get_current_user()


class UpdatePayload(BaseModel):
    ref: str | None = None
    tag: str | None = None


def _require_admin(user: models.User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Brak uprawnień")


def _require_webhook_token(request: Request) -> None:
    expected_token = config.UPDATE_WEBHOOK_TOKEN
    if not expected_token:
        raise HTTPException(status_code=500, detail="Brak konfiguracji tokenu webhooka.")
    provided_token = request.headers.get("x-webhook-token") or request.query_params.get("token")
    if not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(status_code=401, detail="Nieprawidłowy token webhooka.")


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
    task_id = uuid4().hex
    try:
        update_service.claim_update_slot(task_id)
    except update_service.UpdateBlockedError as exc:
        update_service.set_status(
            task_id=task_id,
            status="blocked",
            detail=str(exc),
            progress=0,
        )
        redirect_url = f"/admin?status=update-error&detail={quote_plus(str(exc))}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    try:
        update_service.set_status(
            task_id=task_id,
            status="started",
            detail="Rozpoczęto aktualizację repozytorium.",
            progress=0,
        )
        logger.info(
            "Aktualizacja repozytorium uruchomiona przez użytkownika %s",
            current_user.username,
        )
        try:
            message = updater.sync_repository()
        except updater.UpdateError as exc:
            logger.error(
                "Aktualizacja repozytorium nie powiodła się dla użytkownika %s: %s",
                current_user.username,
                exc,
            )
            update_service.set_status(
                task_id=task_id,
                status="error",
                detail="Aktualizacja repozytorium nie powiodła się.",
                error=str(exc),
            )
            redirect_url = f"/admin?status=update-error&detail={quote_plus(str(exc))}"
            return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        logger.info(
            "Aktualizacja repozytorium zakończona powodzeniem dla użytkownika %s",
            current_user.username,
        )
        update_service.set_status(
            task_id=task_id,
            status="success",
            detail=message,
            progress=100,
        )
        redirect_url = f"/admin?status=update-ok&detail={quote_plus(message)}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    finally:
        update_service.release_update_slot()


@router.post("/update-job")
def trigger_update_job(
    background_tasks: BackgroundTasks,
    payload: UpdatePayload | None = Body(default=None),
    current_user: models.User = Depends(current_user_dep),
) -> dict[str, str | None]:
    _require_admin(current_user)
    payload = payload or UpdatePayload()
    logger.info(
        "Aktualizacja repozytorium (API) uruchomiona przez użytkownika %s",
        current_user.username,
    )
    status_payload = update_service.queue_update(
        background_tasks, ref=payload.ref, tag=payload.tag
    )
    if status_payload.status == "blocked":
        raise HTTPException(status_code=429, detail=status_payload.detail)
    target = payload.ref or (f"tag {payload.tag}" if payload.tag else None)
    return {
        "status": status_payload.status,
        "detail": status_payload.detail,
        "target": target,
        "task_id": status_payload.task_id,
    }


@router.post("/update-start")
def trigger_update_start(
    background_tasks: BackgroundTasks,
    payload: UpdatePayload | None = Body(default=None),
    current_user: models.User = Depends(current_user_dep),
) -> dict[str, str | None]:
    _require_admin(current_user)
    payload = payload or UpdatePayload()
    logger.info(
        "Aktualizacja repozytorium (API) uruchomiona przez użytkownika %s",
        current_user.username,
    )
    status_payload = update_service.queue_update(
        background_tasks, ref=payload.ref, tag=payload.tag
    )
    target = payload.ref or (f"tag {payload.tag}" if payload.tag else None)
    return {
        "status": status_payload.status,
        "detail": status_payload.detail,
        "target": target,
        "task_id": status_payload.task_id,
    }


@router.get("/update-status")
def get_update_status(current_user: models.User = Depends(current_user_dep)) -> dict[str, object]:
    _require_admin(current_user)
    return {
        "status": update_service.read_status(),
        "logs": update_service.read_logs(limit=10),
    }


@router.get("/update-state")
def get_update_state(current_user: models.User = Depends(current_user_dep)) -> dict[str, object | None]:
    _require_admin(current_user)
    return {
        "current": update_service.read_current_state(),
        "last": update_service.read_last_state(),
    }


@router.post("/update/webhook")
def trigger_update_webhook(
    background_tasks: BackgroundTasks,
    request: Request,
    payload: UpdatePayload | None = Body(default=None),
) -> dict[str, str | None]:
    _require_webhook_token(request)
    payload = payload or UpdatePayload()
    logger.info("Webhook uruchomił aktualizację repozytorium.")
    status_payload = update_service.queue_update(
        background_tasks, ref=payload.ref, tag=payload.tag
    )
    if status_payload.status == "blocked":
        raise HTTPException(status_code=429, detail=status_payload.detail)
    target = payload.ref or (f"tag {payload.tag}" if payload.tag else None)
    return {
        "status": status_payload.status,
        "detail": status_payload.detail,
        "target": target,
        "task_id": status_payload.task_id,
    }


@router.get("/update/webhook-status")
def get_update_webhook_status(request: Request, task_id: str | None = None) -> dict[str, object]:
    _require_webhook_token(request)
    status_payload = update_service.read_status()
    if task_id and status_payload and status_payload.get("task_id") != task_id:
        raise HTTPException(status_code=404, detail="Brak statusu dla podanego zadania.")
    return {
        "status": status_payload,
        "logs": update_service.read_logs(limit=10),
    }

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .. import models
from ..db import get_db
from ..security import get_current_user, hash_password
from ..services import db_restore

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

def _cleanup_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass


def _require_admin(user: models.User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Brak uprawnień")


def _render_user_list(
    request: Request,
    db: Session,
    current_user: models.User,
    *,
    message: str | None = None,
    error: str | None = None,
    error_user_id: int | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    users = (
        db.execute(select(models.User).order_by(models.User.username))
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        "users_list.html",
        {
            "request": request,
            "user": current_user,
            "users": users,
            "message": message,
            "error": error,
            "error_user_id": error_user_id,
        },
        status_code=status_code,
    )


def _release_owned_resources(db: Session, user_id: int) -> None:
    for model in (models.Army, models.Roster, models.Weapon, models.Unit, models.Ability):
        db.execute(
            update(model)
            .where(model.owner_id == user_id)
            .values(owner_id=None)
        )


@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    _require_admin(current_user)
    status_key = request.query_params.get("status")
    detail = request.query_params.get("detail")
    message_map = {
        "password-changed": "Hasło użytkownika zostało zaktualizowane.",
        "deleted": "Użytkownik został usunięty.",
        "restore-ok": detail or "Baza danych została przywrócona.",
    }
    message = message_map.get(status_key)

    error_key = request.query_params.get("error")
    error_map = {
        "self-delete": "Nie można usunąć własnego konta.",
        "missing-user": "Użytkownik nie istnieje.",
        "restore-error": detail or "Przywracanie bazy danych nie powiodło się.",
    }
    error = error_map.get(error_key)

    target = request.query_params.get("target")
    error_user_id = int(target) if target and target.isdigit() else None

    return _render_user_list(
        request,
        db,
        current_user,
        message=message,
        error=error,
        error_user_id=error_user_id,
    )


@router.get("/backup")
def download_backup(current_user: models.User = Depends(get_current_user())) -> FileResponse:
    _require_admin(current_user)
    try:
        db_path = db_restore.resolve_sqlite_path()
    except db_restore.DBRestoreError as exc:  # pragma: no cover - guarded by config
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    if not db_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Plik bazy danych nie został znaleziony.",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=db_path.suffix or ".db") as tmp:
        temp_path = Path(tmp.name)

    try:
        with sqlite3.connect(db_path) as source_conn, sqlite3.connect(temp_path) as dest_conn:
            source_conn.backup(dest_conn)
    except sqlite3.Error as exc:
        _cleanup_temp_file(temp_path)
        raise HTTPException(
            status_code=500,
            detail="Nie udało się utworzyć kopii zapasowej bazy danych.",
        ) from exc

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    download_name = f"opr-backup-{timestamp}{temp_path.suffix}"

    background = BackgroundTask(_cleanup_temp_file, temp_path)
    return FileResponse(
        temp_path,
        filename=download_name,
        media_type="application/octet-stream",
        background=background,
    )


@router.post("/{user_id}/password")
def change_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    _require_admin(current_user)
    target_user = db.get(models.User, user_id)
    if not target_user:
        raise HTTPException(status_code=404)

    password = new_password.strip()
    if len(password) < 4:
        return _render_user_list(
            request,
            db,
            current_user,
            error="Hasło musi zawierać co najmniej 4 znaki.",
            error_user_id=user_id,
            status_code=400,
        )

    target_user.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse(url="/users?status=password-changed", status_code=303)


@router.post("/{user_id}/delete")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    _require_admin(current_user)
    target_user = db.get(models.User, user_id)
    if not target_user:
        raise HTTPException(status_code=404)

    if target_user.id == current_user.id:
        return RedirectResponse(
            url=f"/users?error=self-delete&target={user_id}",
            status_code=303,
        )

    _release_owned_resources(db, target_user.id)
    db.delete(target_user)
    db.commit()
    return RedirectResponse(url="/users?status=deleted", status_code=303)


@router.post("/restore")
async def restore_database(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user()),
) -> RedirectResponse:
    _require_admin(current_user)

    try:
        await file.seek(0)
        db_restore.restore_sqlite_database(file)
    except db_restore.DBRestoreError as exc:
        detail = quote_plus(str(exc))
        return RedirectResponse(
            url=f"/users?status=restore-error&detail={detail}",
            status_code=303,
        )
    finally:
        await file.close()

    return RedirectResponse(url="/users?status=restore-ok", status_code=303)

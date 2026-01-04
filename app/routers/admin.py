from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from .. import models
from ..security import get_current_user
from ..services import updater

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _require_admin(user: models.User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Brak uprawnień")


@router.post("/update")
def trigger_update(current_user: models.User = Depends(get_current_user())) -> dict[str, str]:
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "Aktualizacja repozytorium zakończona powodzeniem dla użytkownika %s",
        current_user.username,
    )
    return {"detail": message}

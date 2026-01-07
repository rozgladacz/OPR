from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks

from ..config import DATA_DIR
from . import updater

logger = logging.getLogger(__name__)

_STATUS_FILE = DATA_DIR / "update_status.json"
_LOG_FILE = DATA_DIR / "update_logs.jsonl"


@dataclass(frozen=True)
class UpdateStatus:
    task_id: str
    status: str
    detail: str | None = None
    error: str | None = None
    progress: int | None = None
    updated_at: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(status: UpdateStatus) -> None:
    payload = asdict(status)
    payload["updated_at"] = _now_iso()
    temp_path = _STATUS_FILE.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(_STATUS_FILE)
    _append_log(status)


def _append_log(status: UpdateStatus) -> None:
    message = status.detail or status.error or status.status
    entry = {
        "timestamp": _now_iso(),
        "status": status.status,
        "message": message,
    }
    if status.error:
        entry["error"] = status.error
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_status() -> dict[str, Any] | None:
    if not _STATUS_FILE.exists():
        return None
    try:
        return json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Nie udało się odczytać pliku statusu aktualizacji %s", _STATUS_FILE)
        return None


def read_logs(limit: int = 10) -> list[dict[str, Any]]:
    if not _LOG_FILE.exists():
        return []
    try:
        lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("Nie udało się odczytać logów aktualizacji %s", _LOG_FILE)
        return []
    if limit > 0:
        lines = lines[-limit:]
    logs: list[dict[str, Any]] = []
    for line in lines:
        try:
            logs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return logs


def set_status(
    task_id: str,
    status: str,
    detail: str | None = None,
    error: str | None = None,
    progress: int | None = None,
) -> UpdateStatus:
    payload = UpdateStatus(
        task_id=task_id,
        status=status,
        detail=detail,
        error=error,
        progress=progress,
    )
    _write_status(payload)
    return payload


def queue_update(background_tasks: BackgroundTasks, ref: str | None = None, tag: str | None = None) -> UpdateStatus:
    task_id = uuid4().hex
    status = UpdateStatus(
        task_id=task_id,
        status="queued",
        detail="Zadanie oczekuje na uruchomienie.",
        progress=0,
    )
    _write_status(status)
    background_tasks.add_task(_run_update, task_id, ref, tag)
    return status


def _run_update(task_id: str, ref: str | None, tag: str | None) -> None:
    _write_status(
        UpdateStatus(
            task_id=task_id,
            status="started",
            detail="Rozpoczęto aktualizację repozytorium.",
            progress=0,
        )
    )
    try:
        origin_url = updater._validate_repository()
        target_ref, target_label = updater._resolve_target(ref, tag)
        logger.info("Aktualizacja repozytorium %s do %s", origin_url, target_label)

        _write_status(
            UpdateStatus(
                task_id=task_id,
                status="progress",
                detail="Pobieranie zmian z repozytorium.",
                progress=25,
            )
        )
        updater._run_git_command("fetch", "--all", "--tags", "--prune")

        _write_status(
            UpdateStatus(
                task_id=task_id,
                status="progress",
                detail=f"Resetowanie do {target_label}.",
                progress=75,
            )
        )
        updater._run_git_command("reset", "--hard", target_ref)

        _write_status(
            UpdateStatus(
                task_id=task_id,
                status="success",
                detail=f"Repozytorium zaktualizowane do {target_label}.",
                progress=100,
            )
        )
    except updater.UpdateError as exc:
        logger.error("Aktualizacja repozytorium nie powiodła się: %s", exc)
        _write_status(
            UpdateStatus(
                task_id=task_id,
                status="error",
                detail="Aktualizacja repozytorium nie powiodła się.",
                error=str(exc),
            )
        )
    except Exception as exc:  # pragma: no cover - guard for unexpected failures
        logger.exception("Nieoczekiwany błąd aktualizacji repozytorium")
        _write_status(
            UpdateStatus(
                task_id=task_id,
                status="error",
                detail="Aktualizacja repozytorium nie powiodła się.",
                error=str(exc),
            )
        )

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import close_all_sessions

from ..config import DATA_DIR, DB_URL
from ..db import SessionLocal, engine

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_TABLES = {"users", "armies", "rosters", "units", "weapons"}


def _sqlite_sidecar_paths(db_path: Path) -> tuple[Path, Path]:
    return (
        db_path.with_name(f"{db_path.name}-wal"),
        db_path.with_name(f"{db_path.name}-shm"),
    )


def _remove_sqlite_sidecars(db_path: Path) -> None:
    wal_path, shm_path = _sqlite_sidecar_paths(db_path)
    for sidecar in (wal_path, shm_path):
        with contextlib.suppress(FileNotFoundError):
            deadline = time.monotonic() + 5
            while True:
                try:
                    sidecar.unlink()
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)


def _checkpoint_sqlite(db_path: Path) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error as exc:
        raise DBRestoreError(
            "Nie udało się spójnie przetworzyć dziennika WAL bazy danych."
        ) from exc


class DBRestoreError(Exception):
    """Raised when restoring the database fails."""


def resolve_sqlite_path() -> Path:
    if not DB_URL.startswith("sqlite"):
        raise DBRestoreError(
            "Przywracanie jest dostępne tylko dla bazy danych SQLite."
        )

    raw_path = DB_URL.split("///")[-1]
    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = (_PROJECT_ROOT / db_path).resolve()
    return db_path


def _validate_sqlite_file(path: Path) -> None:
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            cursor = conn.execute(
                f"""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ({",".join(["?"] * len(_REQUIRED_TABLES))})
                """,
                tuple(_REQUIRED_TABLES),
            )
            tables = {row[0] for row in cursor.fetchall()}
    except sqlite3.Error as exc:
        raise DBRestoreError("Przesłany plik nie jest prawidłową bazą SQLite.") from exc

    missing = _REQUIRED_TABLES - tables
    if missing:
        raise DBRestoreError("Brakuje wymaganych tabel w bazie danych.")


def _copy_sqlite_with_sidecars(source: Path, target: Path) -> None:
    _checkpoint_sqlite(source)
    sidecars = _sqlite_sidecar_paths(source)
    target_sidecars = _sqlite_sidecar_paths(target)

    try:
        with sqlite3.connect(source) as source_conn, sqlite3.connect(target) as dest_conn:
            source_conn.backup(dest_conn)
    except sqlite3.Error as exc:
        raise DBRestoreError(
            "Nie udało się utworzyć kopii zapasowej bazy danych."
        ) from exc

    for source_sidecar, target_sidecar in zip(sidecars, target_sidecars):
        if source_sidecar.exists():
            shutil.copy2(source_sidecar, target_sidecar)


def _close_active_sessions() -> None:
    with contextlib.suppress(Exception):
        close_all_sessions()
    engine.dispose()


def _replace_sqlite_db(source: Path, target: Path) -> None:
    _close_active_sessions()
    _checkpoint_sqlite(source)

    deadline = time.monotonic() + 5
    while True:
        try:
            os.replace(source, target)
            break
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)

    _remove_sqlite_sidecars(target)


def restore_sqlite_database(
    upload_file: UploadFile, *, destination_path: Path | None = None
) -> Path:
    if not upload_file:
        raise DBRestoreError("Nie przesłano pliku bazy danych.")

    target_path = destination_path or resolve_sqlite_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=DATA_DIR, suffix=target_path.suffix or ".db"
    )
    os.close(fd)
    temp_path = Path(temp_name)
    wal_temp = temp_path.with_name(f"{temp_path.name}-wal")
    shm_temp = temp_path.with_name(f"{temp_path.name}-shm")

    try:
        upload_file.file.seek(0)
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
            buffer.flush()
            os.fsync(buffer.fileno())

        _validate_sqlite_file(temp_path)
        for sidecar in (wal_temp, shm_temp):
            sidecar.unlink(missing_ok=True)

        _replace_sqlite_db(temp_path, target_path)
        return target_path
    except Exception as exc:
        with contextlib.suppress(FileNotFoundError):
            deadline = time.monotonic() + 5
            while True:
                try:
                    temp_path.unlink(missing_ok=True)
                    wal_temp.unlink(missing_ok=True)
                    shm_temp.unlink(missing_ok=True)
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)

        if isinstance(exc, DBRestoreError):
            raise

        raise DBRestoreError("Nie udało się przywrócić bazy danych.") from exc

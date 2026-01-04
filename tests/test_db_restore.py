from __future__ import annotations

import asyncio
import io
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.datastructures import UploadFile
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.routers import users  # noqa: E402
from app.services import db_restore  # noqa: E402


def _build_request(path: str = "/users/restore") -> Request:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "app": app,
    }
    return Request(scope)


def _build_sqlite_db(path: Path, marker: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("CREATE TABLE armies (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE rosters (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE units (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE weapons (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE markers (label TEXT)")
        conn.execute("INSERT INTO markers(label) VALUES (?)", (marker,))


def _build_sqlite_db_wal(path: Path, marker: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("CREATE TABLE armies (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE rosters (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE units (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE weapons (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE markers (label TEXT)")
        conn.execute("INSERT INTO markers(label) VALUES (?)", (marker,))
        conn.commit()

    wal_path = path.with_name(f"{path.name}-wal")
    shm_path = path.with_name(f"{path.name}-shm")
    assert wal_path.exists()
    assert shm_path.exists()


def test_restore_requires_admin() -> None:
    request = _build_request()
    non_admin = SimpleNamespace(username="user", is_admin=False)
    upload = UploadFile(filename="dummy.db", file=io.BytesIO(b"data"))

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            users.restore_database(request, file=upload, current_user=non_admin)
        )

    assert excinfo.value.status_code == status.HTTP_403_FORBIDDEN


def test_restore_rejects_invalid_sqlite(monkeypatch, tmp_path) -> None:
    target_path = tmp_path / "opr.db"
    _build_sqlite_db(target_path, "old")

    request = _build_request()
    admin = SimpleNamespace(username="admin", is_admin=True)
    upload = UploadFile(filename="invalid.db", file=io.BytesIO(b"not a sqlite"))

    monkeypatch.setattr(db_restore, "resolve_sqlite_path", lambda: target_path)

    response = asyncio.run(
        users.restore_database(request, file=upload, current_user=admin)
    )

    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert query["status"] == ["restore-error"]
    assert target_path.exists()
    with sqlite3.connect(target_path) as conn:
        assert conn.execute("SELECT label FROM markers").fetchone()[0] == "old"


def test_restore_replaces_database(monkeypatch, tmp_path) -> None:
    target_path = tmp_path / "opr.db"
    replacement_path = tmp_path / "replacement.db"
    _build_sqlite_db(target_path, "old")
    _build_sqlite_db(replacement_path, "new")

    request = _build_request()
    admin = SimpleNamespace(username="admin", is_admin=True)
    with open(replacement_path, "rb") as fh:
        upload = UploadFile(filename="replacement.db", file=fh)
        monkeypatch.setattr(db_restore, "resolve_sqlite_path", lambda: target_path)

        response = asyncio.run(
            users.restore_database(request, file=upload, current_user=admin)
        )

    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert query["status"] == ["restore-ok"]
    with sqlite3.connect(target_path) as conn:
        assert conn.execute("SELECT label FROM markers").fetchone()[0] == "new"


def test_backup_copies_wal_sidecars(tmp_path) -> None:
    source_path = tmp_path / "opr.db"
    backup_path = tmp_path / "backup.db"
    _build_sqlite_db_wal(source_path, "wal-marker")

    db_restore._copy_sqlite_with_sidecars(source_path, backup_path)

    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("SELECT label FROM markers").fetchone()[0] == "wal-marker"

    wal_path = backup_path.with_name(f"{backup_path.name}-wal")
    shm_path = backup_path.with_name(f"{backup_path.name}-shm")
    assert wal_path.exists()
    assert shm_path.exists()


def test_restore_removes_old_sidecars(monkeypatch, tmp_path) -> None:
    target_path = tmp_path / "opr.db"
    replacement_path = tmp_path / "replacement.db"
    _build_sqlite_db_wal(target_path, "old")
    _build_sqlite_db(replacement_path, "new")

    # Ensure leftover sidecars exist before restoration.
    target_wal = target_path.with_name(f"{target_path.name}-wal")
    target_shm = target_path.with_name(f"{target_path.name}-shm")
    assert target_wal.exists()
    assert target_shm.exists()

    monkeypatch.setattr(db_restore, "resolve_sqlite_path", lambda: target_path)

    with open(replacement_path, "rb") as fh:
        upload = UploadFile(filename="replacement.db", file=fh)
        asyncio.run(
            users.restore_database(_build_request(), file=upload, current_user=SimpleNamespace(username="admin", is_admin=True))
        )

    assert not target_wal.exists()
    assert not target_shm.exists()
    with sqlite3.connect(target_path) as conn:
        assert conn.execute("SELECT label FROM markers").fetchone()[0] == "new"

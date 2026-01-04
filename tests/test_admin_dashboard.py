from __future__ import annotations

import sys
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.routers import admin  # noqa: E402
from app.services import updater  # noqa: E402


def _build_request(query_string: bytes = b"", path: str = "/admin") -> Request:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": query_string,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "app": app,
    }
    return Request(scope)


def _render_html(response) -> str:
    return response.template.render(response.context)


def test_admin_dashboard_requires_admin() -> None:
    request = _build_request()
    non_admin = SimpleNamespace(username="user", is_admin=False)

    try:
        admin.admin_dashboard(request, current_user=non_admin)
    except HTTPException as exc:
        assert exc.status_code == status.HTTP_403_FORBIDDEN
    else:  # pragma: no cover - safety
        assert False, "Expected HTTPException for non-admin user"


def test_admin_dashboard_renders_messages() -> None:
    admin_user = SimpleNamespace(username="admin", is_admin=True)

    ok_request = _build_request(b"status=update-ok&detail=Zrobione")
    ok_response = admin.admin_dashboard(ok_request, current_user=admin_user)
    ok_html = _render_html(ok_response)
    assert "alert alert-success" in ok_html
    assert "Zrobione" in ok_html

    error_request = _build_request(b"status=update-error&detail=Blad")
    error_response = admin.admin_dashboard(error_request, current_user=admin_user)
    error_html = _render_html(error_response)
    assert "alert alert-danger" in error_html
    assert "Blad" in error_html


def test_admin_update_redirects_with_success(monkeypatch) -> None:
    admin_user = SimpleNamespace(username="admin", is_admin=True)
    request = _build_request(path="/admin/update")

    monkeypatch.setattr(admin.updater, "sync_repository", lambda: "Zaktualizowano")

    response = admin.trigger_update(request, current_user=admin_user)

    assert response.status_code == status.HTTP_303_SEE_OTHER
    parsed = urlparse(response.headers["location"])
    assert parsed.path == "/admin"
    query = parse_qs(parsed.query)
    assert query["status"] == ["update-ok"]
    assert query["detail"] == ["Zaktualizowano"]

    follow_request = _build_request(parsed.query.encode(), path=parsed.path)
    follow_response = admin.admin_dashboard(follow_request, current_user=admin_user)
    follow_html = _render_html(follow_response)
    assert "alert alert-success" in follow_html
    assert "Zaktualizowano" in follow_html


def test_admin_update_redirects_with_error(monkeypatch) -> None:
    admin_user = SimpleNamespace(username="admin", is_admin=True)
    request = _build_request(path="/admin/update")

    def raise_error():
        raise updater.UpdateError("Niepowodzenie")

    monkeypatch.setattr(admin.updater, "sync_repository", raise_error)

    response = admin.trigger_update(request, current_user=admin_user)

    assert response.status_code == status.HTTP_303_SEE_OTHER
    parsed = urlparse(response.headers["location"])
    assert parsed.path == "/admin"
    query = parse_qs(parsed.query)
    assert query["status"] == ["update-error"]
    assert query["detail"] == ["Niepowodzenie"]

    follow_request = _build_request(parsed.query.encode(), path=parsed.path)
    follow_response = admin.admin_dashboard(follow_request, current_user=admin_user)
    follow_html = _render_html(follow_response)
    assert "alert alert-danger" in follow_html
    assert "Niepowodzenie" in follow_html

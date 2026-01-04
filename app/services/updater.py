from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ..config import UPDATE_BRANCH, UPDATE_REPO_URL

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class UpdateError(Exception):
    """Raised when updating the repository fails."""


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _run_git_command(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment guard
        raise UpdateError("Polecenie git jest niedostępne w systemie.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        stdout = exc.stdout.strip()
        error_message = stderr or stdout or "Polecenie git zakończyło się niepowodzeniem."
        raise UpdateError(error_message) from exc
    return result.stdout.strip()


def _determine_branch() -> str:
    branch = UPDATE_BRANCH or _run_git_command("rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        raise UpdateError("Nie można ustalić docelowej gałęzi do aktualizacji.")
    return branch


def _validate_repository() -> str:
    if not UPDATE_REPO_URL:
        raise UpdateError("Brak skonfigurowanego adresu repozytorium (UPDATE_REPO_URL).")

    git_dir = _PROJECT_ROOT / ".git"
    if not git_dir.exists():
        raise UpdateError("Katalog projektu nie jest repozytorium Git.")

    origin_url = _run_git_command("remote", "get-url", "origin")
    if _normalize_url(origin_url) != _normalize_url(UPDATE_REPO_URL):
        raise UpdateError("Skonfigurowany adres repozytorium nie jest zgodny z origin.")

    return origin_url


def sync_repository() -> str:
    origin_url = _validate_repository()
    branch = _determine_branch()

    logger.info(
        "Rozpoczynam aktualizację repozytorium %s do gałęzi origin/%s", origin_url, branch
    )
    _run_git_command("fetch", "--all", "--prune")
    _run_git_command("reset", "--hard", f"origin/{branch}")
    logger.info("Repozytorium zostało zresetowane do origin/%s", branch)

    return f"Repozytorium zaktualizowane do origin/{branch}."

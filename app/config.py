import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SECRET_KEY = os.getenv("SECRET_KEY", "jakis_dlugi_i_sekretny_klucz_po_polsku_dla_zmylki")
DB_URL = os.getenv("DB_URL", "sqlite:///./data/opr.db")
DEBUG = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"}
UPDATE_REPO_URL = os.getenv("UPDATE_REPO_URL", "https://github.com/rozgladacz/OPR")
UPDATE_BRANCH = os.getenv("UPDATE_BRANCH", "main")
UPDATE_REPO_PATH = os.getenv("UPDATE_REPO_PATH", ".")
UPDATE_REF = os.getenv("UPDATE_REF", "")
UPDATE_DOCKERFILE = os.getenv("UPDATE_DOCKERFILE", "Dockerfile")
UPDATE_COMPOSE_FILE = os.getenv("UPDATE_COMPOSE_FILE", "docker-compose.yml")


def _load_json_list(env_key: str, default: list) -> list:
    raw_value = os.getenv(env_key)
    if not raw_value:
        return default
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return default
    return parsed if isinstance(parsed, list) else default


COMMAND_RUNNER_ALLOWED_COMMANDS = _load_json_list("COMMAND_RUNNER_ALLOWED_COMMANDS", [])
COMMAND_RUNNER_SEQUENCE = _load_json_list("COMMAND_RUNNER_SEQUENCE", [])
COMMAND_RUNNER_WORKDIR = Path(os.getenv("COMMAND_RUNNER_WORKDIR", "."))

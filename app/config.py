import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please-very-secret-key")
DB_URL = os.getenv("DB_URL", "sqlite:///./data/opr.db")
DEBUG = os.getenv("DEBUG", "true").lower() in {"1", "true", "yes"}

UPDATE_REPO_URL = os.getenv("UPDATE_REPO_URL")
UPDATE_BRANCH = os.getenv("UPDATE_BRANCH")

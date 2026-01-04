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
UPDATE_BRANCH = os.getenv("UPDATE_BRANCH", "ain")

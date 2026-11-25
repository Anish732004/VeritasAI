"""Paths and environment settings. Secrets live in .env and never reach the browser."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("VERITAS_DB", DATA_DIR / "veritas.db"))
JOURNAL_LIST_PATH = DATA_DIR / "journal_list.csv"
CONFERENCE_LIST_PATH = DATA_DIR / "conference_list.csv"
STATIC_DIR = ROOT / "static"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "").strip()
# OpenAlex and Crossref ask API clients to identify themselves with a contact address
# ("polite pool"). Optional; set it in .env, it is only sent to those two services.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "").strip()

APP_VERSION = "2.0.0"
PROMPT_VERSION = "2026-11-25.1"
HTTP_TIMEOUT = float(os.getenv("VERITAS_HTTP_TIMEOUT", "20"))
CACHE_TTL_SECONDS = 24 * 3600

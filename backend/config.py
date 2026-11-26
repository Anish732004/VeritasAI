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

# Language model (optional). NVIDIA's API catalog (build.nvidia.com) or OpenAI; both use the same
# chat-completions protocol. With an NVIDIA key set, NVIDIA is used unless AI_PROVIDER says otherwise.
AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
# OpenAI model names never contain "/", so an NVIDIA catalog name put in OPENAI_MODEL is honoured too.
_openai_model_env = os.getenv("OPENAI_MODEL", "").strip()
NVIDIA_MODEL = (os.getenv("NVIDIA_MODEL", "").strip() or (_openai_model_env if "/" in _openai_model_env else "")
                or "nvidia/nemotron-3.5-lightning-30b-a3b")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "").strip() or "https://integrate.api.nvidia.com/v1"
# Reasoning ("thinking") mode for NVIDIA models: off unless AI_THINKING=on (slower, rarely better for these tasks).
AI_THINKING = os.getenv("AI_THINKING", "").strip().lower() in ("1", "on", "true", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "").strip()
# OpenAlex and Crossref ask API clients to identify themselves with a contact address
# ("polite pool"). Optional; set it in .env, it is only sent to those two services.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "").strip()

APP_VERSION = "2.0.0"
PROMPT_VERSION = "2026-11-26.1"
HTTP_TIMEOUT = float(os.getenv("VERITAS_HTTP_TIMEOUT", "20"))
CACHE_TTL_SECONDS = 24 * 3600

"""Entry point: `python -m uvicorn server:app --host 127.0.0.1 --port 8000`.

The application lives in the `backend/` package; this file only builds it.
Keep the server bound to 127.0.0.1: it has no login and is meant for one local user.
"""
from backend.api import create_app

app = create_app()

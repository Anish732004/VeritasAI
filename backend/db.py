"""SQLite persistence following the blueprint's core data model (section 7).

SQLite keeps the prototype dependency-free; the schema maps one-to-one onto PostgreSQL
tables if the project moves to a hosted database later.
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, question TEXT NOT NULL, scope TEXT DEFAULT '',
  level TEXT DEFAULT '', status TEXT DEFAULT 'active', plan TEXT, plan_approved_at TEXT,
  summary TEXT, exported_at TEXT, challenged_at TEXT, demo INTEGER DEFAULT 0, created_at TEXT
);

CREATE TABLE IF NOT EXISTS refs (
  id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL, authors TEXT DEFAULT '[]', year TEXT DEFAULT '', doi TEXT DEFAULT '',
  journal TEXT DEFAULT '', issn TEXT DEFAULT '[]', volume TEXT DEFAULT '', issue TEXT DEFAULT '',
  pages TEXT DEFAULT '', url TEXT DEFAULT '', abstract TEXT DEFAULT '', fulltext TEXT DEFAULT '',
  fulltext_origin TEXT DEFAULT '', metadata_source TEXT DEFAULT 'manual', external_id TEXT DEFAULT '',
  record TEXT, original TEXT, retrieved_at TEXT, discovery TEXT, venue TEXT,
  folder TEXT DEFAULT '', tags TEXT DEFAULT '[]', notes TEXT DEFAULT '',
  decision TEXT DEFAULT 'Pending', decision_reason TEXT DEFAULT '',
  verification_status TEXT DEFAULT 'Pending review', verification_id TEXT,
  override_reason TEXT DEFAULT '', demo INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT,
  kind TEXT DEFAULT 'journal-article'
);

CREATE TABLE IF NOT EXISTS verification_results (
  id TEXT PRIMARY KEY, reference_id TEXT REFERENCES refs(id) ON DELETE CASCADE,
  status TEXT, reason TEXT, fields TEXT, matched_fields TEXT, discrepancies TEXT,
  searched TEXT, record TEXT, suggestions TEXT, checked_at TEXT
);

CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  text TEXT NOT NULL, claim_type TEXT DEFAULT 'source_finding', status TEXT, status_reason TEXT,
  evidence_level TEXT DEFAULT '', decision TEXT DEFAULT 'Pending', decision_reason TEXT DEFAULT '',
  created_by TEXT DEFAULT 'student', demo INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS evidence_records (
  id TEXT PRIMARY KEY, claim_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
  reference_id TEXT REFERENCES refs(id) ON DELETE CASCADE, passage TEXT, location TEXT,
  page TEXT DEFAULT '', section TEXT DEFAULT '', match TEXT, match_score REAL,
  stance TEXT DEFAULT 'supports', stance_method TEXT DEFAULT 'student', origin TEXT DEFAULT 'student',
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS review_decisions (
  id TEXT PRIMARY KEY, actor TEXT, object_type TEXT, object_id TEXT, decision TEXT,
  reason TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, project_id TEXT, actor TEXT, action TEXT, object_type TEXT,
  object_id TEXT, details TEXT, ai TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY, project_id TEXT, agent TEXT, status TEXT, input TEXT,
  output_summary TEXT, error TEXT, started_at TEXT, finished_at TEXT
);

CREATE TABLE IF NOT EXISTS chat (
  id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  question TEXT, answer TEXT, ai TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS api_cache (key TEXT PRIMARY KEY, value TEXT, fetched_at REAL);

CREATE INDEX IF NOT EXISTS idx_refs_project ON refs(project_id);
CREATE INDEX IF NOT EXISTS idx_claims_project ON claims(project_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence_records(claim_id);
CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_events(project_id);
"""

JSON_COLUMNS = {
    "plan", "summary", "authors", "issn", "record", "original", "discovery", "venue", "tags",
    "fields", "matched_fields", "discrepancies", "searched", "suggestions", "input", "ai", "details_json",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextmanager
def db():
    con = _connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with db() as con:
        con.executescript(SCHEMA)
        # Small migrations for databases created by earlier versions.
        have = {r["name"] for r in con.execute("PRAGMA table_info(refs)")}
        if "kind" not in have:
            con.execute("ALTER TABLE refs ADD COLUMN kind TEXT DEFAULT 'journal-article'")


def row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    out = dict(r)
    for k in JSON_COLUMNS & out.keys():
        if isinstance(out[k], str) and out[k]:
            try:
                out[k] = json.loads(out[k])
            except ValueError:
                pass
    return out


def rows(rs) -> list[dict]:
    return [row(r) for r in rs]


def dump(value) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def insert(con, table: str, data: dict) -> dict:
    data = {k: (dump(v) if k in JSON_COLUMNS else v) for k, v in data.items()}
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    con.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(data.values()))
    return data


def update(con, table: str, id_: str, data: dict) -> None:
    if not data:
        return
    data = {k: (dump(v) if k in JSON_COLUMNS else v) for k, v in data.items()}
    sets = ", ".join(f"{k} = ?" for k in data)
    con.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*data.values(), id_])


def get(con, table: str, id_: str) -> dict | None:
    return row(con.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone())


def setting(con, key: str, default=None):
    r = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(con, key: str, value) -> None:
    con.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def audit(con, action: str, *, actor: str = "Student", project_id: str | None = None,
          object_type: str = "", object_id: str = "", details: str = "", ai: dict | None = None) -> None:
    insert(con, "audit_events", {
        "id": new_id(), "project_id": project_id, "actor": actor, "action": action,
        "object_type": object_type, "object_id": object_id, "details": details[:2000],
        "ai": ai, "created_at": now(),
    })


def decision(con, object_type: str, object_id: str, value: str, reason: str = "", actor: str = "Student") -> None:
    insert(con, "review_decisions", {
        "id": new_id(), "actor": actor, "object_type": object_type, "object_id": object_id,
        "decision": value, "reason": reason, "created_at": now(),
    })

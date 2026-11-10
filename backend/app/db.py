"""SQLite persistence: projects, sketches and versions (full Version JSON per row)."""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

DB_PATH = config.DATA_DIR / "neurogenui.db"
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sketches (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  width INTEGER, height INTEGER,
  analysis TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  number INTEGER NOT NULL,
  parent INTEGER,
  kind TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (project_id, number)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


@contextmanager
def connect():
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


# --------------------------------------------------------------------------- projects

def create_project(name: str) -> dict:
    pid, ts = new_id("p"), now()
    with connect() as conn:
        conn.execute("INSERT INTO projects VALUES (?,?,?,?)", (pid, name.strip() or "Untitled project", ts, ts))
    return get_project_row(pid)


def get_project_row(pid: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return dict(row) if row else None


def list_project_rows() -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY updated_at DESC")]


def rename_project(pid: str, name: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE projects SET name=?, updated_at=? WHERE id=?", (name, now(), pid))


def touch_project(pid: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))


def delete_project(pid: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    return cur.rowcount > 0


# --------------------------------------------------------------------------- sketches

def add_sketch(project_id: str, filename: str, width: int, height: int, sketch_id: str | None = None) -> dict:
    sid = sketch_id or new_id("s")
    with connect() as conn:
        conn.execute("INSERT INTO sketches VALUES (?,?,?,?,?,?,?)", (sid, project_id, filename, width, height, None, now()))
    return get_sketch(sid)


def get_sketch(sid: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sketches WHERE id=?", (sid,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["analysis"] = json.loads(out["analysis"]) if out["analysis"] else None
    return out


def latest_sketch(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT id FROM sketches WHERE project_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                           (project_id,)).fetchone()
    return get_sketch(row["id"]) if row else None


def save_analysis(sid: str, analysis: dict) -> None:
    with connect() as conn:
        conn.execute("UPDATE sketches SET analysis=? WHERE id=?", (json.dumps(analysis), sid))


# --------------------------------------------------------------------------- versions

def next_version_number(project_id: str) -> int:
    with connect() as conn:
        row = conn.execute("SELECT MAX(number) AS n FROM versions WHERE project_id=?", (project_id,)).fetchone()
    return (row["n"] or 0) + 1


def save_version(version: dict) -> dict:
    with connect() as conn:
        if not version.get("number"):
            row = conn.execute("SELECT MAX(number) AS n FROM versions WHERE project_id=?", (version["project_id"],)).fetchone()
            version["number"] = (row["n"] or 0) + 1
        version.setdefault("created_at", now())
        conn.execute("INSERT INTO versions VALUES (?,?,?,?,?,?)",
                     (version["project_id"], version["number"], version.get("parent"), version["kind"],
                      json.dumps(version), version["created_at"]))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (version["created_at"], version["project_id"]))
    return version


def update_version(version: dict) -> None:
    with connect() as conn:
        conn.execute("UPDATE versions SET data=? WHERE project_id=? AND number=?",
                     (json.dumps(version), version["project_id"], version["number"]))


def get_version(project_id: str, number: int | None = None) -> dict | None:
    with connect() as conn:
        if number is None:
            row = conn.execute("SELECT data FROM versions WHERE project_id=? ORDER BY number DESC LIMIT 1",
                               (project_id,)).fetchone()
        else:
            row = conn.execute("SELECT data FROM versions WHERE project_id=? AND number=?", (project_id, number)).fetchone()
    return json.loads(row["data"]) if row else None


def list_versions(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT data FROM versions WHERE project_id=? ORDER BY number", (project_id,)).fetchall()
    return [json.loads(r["data"]) for r in rows]


def version_count(project_id: str) -> tuple[int, int | None]:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c, MAX(number) AS n FROM versions WHERE project_id=?", (project_id,)).fetchone()
    return row["c"], row["n"]

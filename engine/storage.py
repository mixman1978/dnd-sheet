# engine/storage.py
"""Persistenza personaggi.

Backend: SQLite (default) con migrazione automatica dai vecchi JSON in db/characters/*.json.

API pubblica usata da main.py:
    - list_characters() -> list[str]
    - save_character(name: str, pg: dict) -> str
    - load_character(key: str) -> dict
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable


# -------------------------
# Paths
# -------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # .../dnd-sheet
DB_ROOT = PROJECT_ROOT / "db"
JSON_DIR = DB_ROOT / "characters"  # legacy
SQLITE_PATH = DB_ROOT / "dnd_sheet.sqlite3"


# -------------------------
# SQLite helpers
# -------------------------
def _connect() -> sqlite3.Connection:
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            data_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);")
    conn.commit()


def _upsert_character(conn: sqlite3.Connection, name: str, pg: dict) -> None:
    payload = json.dumps(pg, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO characters(name, data_json, updated_at)
        VALUES(?, ?, datetime('now'))
        ON CONFLICT(name) DO UPDATE SET
            data_json=excluded.data_json,
            updated_at=datetime('now');
        """,
        (name, payload),
    )
    conn.commit()


def _fetch_names(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT name FROM characters ORDER BY name COLLATE NOCASE;")
    return [r["name"] for r in cur.fetchall()]


def _fetch_character(conn: sqlite3.Connection, name: str) -> dict | None:
    cur = conn.execute("SELECT data_json FROM characters WHERE name=?;", (name,))
    row = cur.fetchone()
    if not row:
        return None
    return json.loads(row["data_json"])


# -------------------------
# Legacy JSON migration
# -------------------------
def _iter_legacy_json_files() -> Iterable[Path]:
    if not JSON_DIR.exists():
        return []
    return sorted(JSON_DIR.glob("*.json"))


def _migrate_legacy_json(conn: sqlite3.Connection) -> None:
    """Importa i vecchi JSON in SQLite (se presenti).

    - Non sovrascrive un personaggio già presente in tabella.
    - Il nome viene preso da pg['nome'] se disponibile, altrimenti dal filename.
    """
    files = list(_iter_legacy_json_files())
    if not files:
        return

    existing = set(_fetch_names(conn))

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
        except Exception:
            continue

        name = (str(data.get("nome") or "").strip()) or path.stem
        if name in existing:
            continue

        _upsert_character(conn, name, data)
        existing.add(name)


def _use_sqlite_backend() -> bool:
    """Decide backend.

    Default: SQLite.
    Puoi forzare JSON con env var DND_STORAGE=json.
    """
    forced = (os.getenv("DND_STORAGE") or "").strip().lower()
    if forced == "json":
        return False
    return True


# -------------------------
# Public API
# -------------------------
def list_characters() -> list[str]:
    """Ritorna lista nomi personaggi."""
    if not _use_sqlite_backend():
        # fallback legacy
        JSON_DIR.mkdir(parents=True, exist_ok=True)
        return sorted([p.name for p in JSON_DIR.glob("*.json")])

    with _connect() as conn:
        _init_db(conn)
        _migrate_legacy_json(conn)
        return _fetch_names(conn)


def save_character(name: str, pg: dict) -> str:
    """Salva (upsert) e ritorna la chiave/nome salvato."""
    clean = (name or "personaggio").strip() or "personaggio"

    if not _use_sqlite_backend():
        JSON_DIR.mkdir(parents=True, exist_ok=True)
        safe = clean.replace(" ", "_")
        path = JSON_DIR / f"{safe}.json"
        path.write_text(json.dumps(pg, ensure_ascii=False, indent=2), encoding="utf-8")
        return path.name

    with _connect() as conn:
        _init_db(conn)
        # assicuriamoci che il nome nel payload sia coerente
        if isinstance(pg, dict):
            pg["nome"] = clean
        _upsert_character(conn, clean, pg)
    return clean


def load_character(key: str) -> dict:
    """Carica un personaggio.

    Con backend SQLite, `key` è il nome personaggio.
    Per compatibilità: se arriva un filename .json ed esiste in legacy dir, lo legge.
    """
    k = (key or "").strip()
    if not k:
        return {}

    # compat legacy: se è un file JSON esplicito
    if k.lower().endswith(".json"):
        path = JSON_DIR / k
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        k = Path(k).stem

    if not _use_sqlite_backend():
        path = JSON_DIR / f"{k}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    with _connect() as conn:
        _init_db(conn)
        _migrate_legacy_json(conn)
        data = _fetch_character(conn, k)
        return data or {}

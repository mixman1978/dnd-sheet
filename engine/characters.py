from __future__ import annotations

import json

from engine.db import connect, ensure_schema


def list_characters() -> list[dict]:
    """Return saved characters with minimal metadata for the UI."""
    with connect() as conn:
        ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT id, name, updated_at
            FROM characters
            ORDER BY datetime(updated_at) DESC, id DESC
            """
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "name": str(r["name"]),
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def save_character(name: str, data: dict) -> int:
    """Upsert by name, updating updated_at, and return the character id."""
    payload = json.dumps(data, ensure_ascii=False)
    clean_name = (name or "personaggio").strip() or "personaggio"

    with connect() as conn:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO characters (name, data_json, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(name) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = datetime('now')
            """,
            (clean_name, payload),
        )
        row = conn.execute(
            "SELECT id FROM characters WHERE name = ?",
            (clean_name,),
        ).fetchone()
        conn.commit()

    return int(row["id"]) if row else 0


def get_character_id_by_name(name: str) -> int | None:
    clean_name = (name or "").strip()
    if not clean_name:
        return None
    with connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT id FROM characters WHERE name = ?",
            (clean_name,),
        ).fetchone()
    return int(row["id"]) if row else None


def load_character(char_id: int) -> dict | None:
    """Load a character by id and return the parsed JSON payload."""
    with connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT data_json FROM characters WHERE id = ?",
            (char_id,),
        ).fetchone()

    if not row:
        return None

    try:
        data = json.loads(row["data_json"])
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def delete_character(char_id: int) -> None:
    """Delete a character by id."""
    with connect() as conn:
        ensure_schema(conn)
        conn.execute("DELETE FROM characters WHERE id = ?", (char_id,))
        conn.commit()


def purge_characters() -> int:
    """Delete all characters and return the number of deleted rows."""
    with connect() as conn:
        ensure_schema(conn)
        cur = conn.execute("DELETE FROM characters")
        conn.commit()
        return int(cur.rowcount or 0)

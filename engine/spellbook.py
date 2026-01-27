from __future__ import annotations

from engine.db import connect, ensure_schema
from engine.spells_repo import list_by_character


def list_character_spells(character_id: int) -> list[dict]:
    return list_by_character(character_id)


def add_spell_to_character(character_id: int, spell_id: int) -> None:
    with connect() as conn:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO character_spells (character_id, spell_id, status)
            VALUES (?, ?, 'known')
            """,
            (int(character_id), int(spell_id)),
        )
        conn.commit()


def remove_spell_from_character(character_id: int, spell_id: int) -> None:
    with connect() as conn:
        ensure_schema(conn)
        conn.execute(
            """
            DELETE FROM character_spells
            WHERE character_id = ? AND spell_id = ? AND status = 'known'
            """,
            (int(character_id), int(spell_id)),
        )
        conn.commit()

from __future__ import annotations

from typing import Iterable

from engine.db import connect, ensure_schema


def _rows_to_spells(rows: Iterable) -> list[dict]:
    return [
        {
            "id": int(r["id"]),
            "name": str(r["name_it"]),
            "level": int(r["level"]),
            "school": str(r["school"]),
        }
        for r in rows
    ]


def search_spells(q: str, level: int | None = None, class_name: str | None = None, limit: int = 20) -> list[dict]:
    if not q:
        return []

    like = f"%{q.strip()}%"
    params: list = [like]
    level_filter = ""
    class_join = ""
    class_filter = ""

    if level is not None:
        level_filter = "AND s.level = ?"
        params.append(int(level))

    if class_name:
        class_join = "JOIN spell_classes sc ON sc.spell_id = s.id JOIN classes c ON c.code = sc.class_code"
        class_filter = "AND c.name_it = ?"
        params.append(class_name)

    with connect() as conn:
        ensure_schema(conn)
        rows = conn.execute(
            f"""
            SELECT s.id, s.name_it, s.level, s.school
            FROM spells s
            {class_join}
            WHERE s.name_it LIKE ?
            {level_filter}
            {class_filter}
            ORDER BY s.level ASC, s.name_it ASC
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()

    return _rows_to_spells(rows)


def list_by_character(character_id: int) -> list[dict]:
    with connect() as conn:
        ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT s.id, s.name_it, s.level, s.school
            FROM character_spells cs
            JOIN spells s ON s.id = cs.spell_id
            WHERE cs.character_id = ? AND cs.status = 'known'
            ORDER BY s.level ASC, s.name_it ASC
            """,
            (int(character_id),),
        ).fetchall()

    return _rows_to_spells(rows)


def get_by_id(spell_id: int) -> dict | None:
    with connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            """
            SELECT
                id,
                name_it,
                level,
                school,
                casting_time,
                range_text,
                components_v,
                components_s,
                components_m,
                material_text,
                duration_text,
                concentration,
                ritual,
                description,
                at_higher_levels
            FROM spells
            WHERE id = ?
            """,
            (int(spell_id),),
        ).fetchone()

    if not row:
        return None

    components = []
    if row["components_v"]:
        components.append("V")
    if row["components_s"]:
        components.append("S")
    if row["components_m"]:
        components.append("M")
    components_text = ", ".join(components) if components else "-"
    if row["components_m"] and row["material_text"]:
        components_text = f"{components_text} ({row['material_text']})"

    return {
        "id": int(row["id"]),
        "name": row["name_it"],
        "level": int(row["level"]),
        "school": row["school"],
        "casting_time": row["casting_time"],
        "range_text": row["range_text"],
        "components_text": components_text,
        "duration_text": row["duration_text"],
        "concentration": bool(row["concentration"]),
        "ritual": bool(row["ritual"]),
        "description": row["description"],
        "at_higher_levels": row["at_higher_levels"],
    }

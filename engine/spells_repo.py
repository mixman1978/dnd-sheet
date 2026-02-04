from __future__ import annotations

import re
from typing import Iterable

from engine.db import connect, ensure_schema


def _rows_to_spells(rows: Iterable) -> list[dict]:
    spells = []
    for r in rows:
        item = {
            "id": int(r["id"]),
            "name": str(r["name_it"]),
            "level": int(r["level"]),
            "school": str(r["school"]),
        }
        if "class_codes" in r.keys():
            item["class_codes"] = r["class_codes"] or ""
        spells.append(item)
    return spells


def search_spells(
    q: str,
    level: int | None = None,
    class_code: str | None = None,
    limit: int = 20,
) -> list[dict]:
    params: list = []
    where: list[str] = []

    q = (q or "").strip()
    if q:
        where.append("s.name_it LIKE ?")
        params.append(f"%{q}%")

    if level is not None:
        where.append("s.level = ?")
        params.append(int(level))

    if class_code:
        where.append(
            "EXISTS (SELECT 1 FROM spell_classes sc_filter WHERE sc_filter.spell_id = s.id AND sc_filter.class_code = ?)"
        )
        params.append(class_code)

    with connect() as conn:
        ensure_schema(conn)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = conn.execute(
            f"""
            SELECT s.id, s.name_it, s.level, s.school, group_concat(DISTINCT sc_all.class_code) AS class_codes
            FROM spells s
            LEFT JOIN spell_classes sc_all ON sc_all.spell_id = s.id
            {where_sql}
            GROUP BY s.id
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
            SELECT
                s.id,
                s.name_it,
                s.level,
                s.school,
                group_concat(DISTINCT sc.class_code) AS class_codes
            FROM character_spells cs
            JOIN spells s ON s.id = cs.spell_id
            LEFT JOIN spell_classes sc ON sc.spell_id = s.id
            WHERE cs.character_id = ? AND cs.status = 'known'
            GROUP BY s.id
            ORDER BY s.level ASC, s.name_it ASC
            """,
            (int(character_id),),
        ).fetchall()

    return _rows_to_spells(rows)


_ACTION_TYPE_MAP = {
    "action": "1 azione",
    "bonus_action": "1 azione bonus",
    "bonus action": "1 azione bonus",
    "reaction": "1 reazione",
}


def _display_casting_time(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    return _ACTION_TYPE_MAP.get(raw.lower(), raw)


def _display_range_text(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    if raw.lower() in {"self", "incantatore"}:
        return "Incantatore"
    return raw


def _clean_description(description: str | None, duration_text: str | None) -> str:
    text = (description or "").strip()
    if not text:
        return "—"

    # OCR residue: "ora Per ..."
    text = re.sub(r"^\s*ora\s+(?=Per\b)", "", text, flags=re.IGNORECASE).strip()

    duration = (duration_text or "").strip()
    if duration:
        candidates = [duration]
        if "," in duration:
            tail = duration.split(",")[-1].strip()
            if tail:
                candidates.append(tail)

        for cand in candidates:
            pat = re.compile(rf"^\s*{re.escape(cand)}(?:\s+|[:;,\-])+", flags=re.IGNORECASE)
            if pat.match(text):
                text = pat.sub("", text, count=1).strip()
                break

    return text or "—"


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
                at_higher_levels,
                (
                    SELECT group_concat(DISTINCT sc.class_code)
                    FROM spell_classes sc
                    WHERE sc.spell_id = spells.id
                ) AS class_codes
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
        "casting_time": _display_casting_time(row["casting_time"]),
        "range_text": _display_range_text(row["range_text"]),
        "components_text": components_text,
        "duration_text": row["duration_text"],
        "concentration": bool(row["concentration"]),
        "ritual": bool(row["ritual"]),
        "description": _clean_description(row["description"], row["duration_text"]),
        "at_higher_levels": row["at_higher_levels"],
        "class_codes": row["class_codes"] or "",
    }

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from engine.db import connect, ensure_schema

PRIVATE_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "private_spells.sqlite3"


def _rows_to_spells(rows: Iterable) -> list[dict]:
    spells = []
    for r in rows:
        item = {
            "id": int(r["id"]),
            "name": str(r["name_it"]),
            "level": int(r["level"]),
            "school": str(r["school"]),
            "ritual": bool(r["ritual"]) if "ritual" in r.keys() else False,
            "concentration": bool(r["concentration"]) if "concentration" in r.keys() else False,
        }
        if "origin" in r.keys():
            item["origin"] = str(r["origin"] or "srd")
        else:
            item["origin"] = "srd"
        if "spell_key" in r.keys():
            item["spell_key"] = str(r["spell_key"])
        else:
            item["spell_key"] = f"{item['origin']}:{item['id']}"
        if "class_codes" in r.keys():
            item["class_codes"] = r["class_codes"] or ""
        spells.append(item)
    return spells


def search_spells(
    q: str,
    level: int | None = None,
    class_code: str | None = None,
    class_codes: Sequence[str] | None = None,
    max_level: int | None = None,
    ritual_only: bool = False,
    concentration_only: bool = False,
    include_private: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    params: list = []
    where: list[str] = []

    q = (q or "").strip()
    if q:
        where.append("u.name_it LIKE ?")
        params.append(f"%{q}%")

    if level is not None:
        where.append("u.level = ?")
        params.append(int(level))
    if max_level is not None:
        where.append("u.level <= ?")
        params.append(int(max_level))
    if ritual_only:
        where.append("u.ritual = 1")
    if concentration_only:
        where.append("u.concentration = 1")

    class_code_single = (class_code or "").strip().lower() or None
    unique_codes: list[str] = []
    seen: set[str] = set()
    for raw in (class_codes or []):
        code = (raw or "").strip().lower()
        if code and code not in seen:
            unique_codes.append(code)
            seen.add(code)

    with connect() as conn:
        ensure_schema(conn)
        private_attached = False
        if include_private and PRIVATE_DB_PATH.exists():
            attached = {row[1] for row in conn.execute("PRAGMA database_list").fetchall()}
            if "priv" not in attached:
                conn.execute("ATTACH DATABASE ? AS priv", (str(PRIVATE_DB_PATH),))
            private_attached = True

        union_sql = """
            SELECT
                s.id AS id,
                'srd' AS origin,
                'srd:' || s.id AS spell_key,
                s.name_it,
                s.level,
                s.school,
                s.ritual,
                s.concentration
            FROM main.spells s
        """
        if private_attached:
            union_sql += """
            UNION ALL
            SELECT
                p.id AS id,
                'private' AS origin,
                'private:' || p.id AS spell_key,
                p.name_it,
                p.level,
                p.school,
                p.ritual,
                p.concentration
            FROM priv.spells p
            """

        if class_code_single:
            class_filter = """
                EXISTS (
                    SELECT 1
                    FROM main.spell_classes sc_filter
                    WHERE u.origin = 'srd'
                      AND sc_filter.spell_id = u.id
                      AND sc_filter.class_code = ?
                )
            """
            if private_attached:
                class_filter = """
                    (
                        EXISTS (
                            SELECT 1
                            FROM main.spell_classes sc_filter
                            WHERE u.origin = 'srd'
                              AND sc_filter.spell_id = u.id
                              AND sc_filter.class_code = ?
                        )
                        OR (
                            u.origin = 'private'
                            AND (
                                EXISTS (
                                    SELECT 1
                                    FROM priv.spell_classes scp_filter
                                    WHERE scp_filter.spell_id = u.id
                                      AND scp_filter.class_code = ?
                                )
                            )
                        )
                    )
                """
            where.append(" ".join(class_filter.split()))
            params.append(class_code_single)
            if private_attached:
                params.append(class_code_single)

        if unique_codes:
            placeholders = ", ".join("?" for _ in unique_codes)
            class_filter_list = f"""
                EXISTS (
                    SELECT 1
                    FROM main.spell_classes sc_filter_list
                    WHERE u.origin = 'srd'
                      AND sc_filter_list.spell_id = u.id
                      AND sc_filter_list.class_code IN ({placeholders})
                )
            """
            if private_attached:
                class_filter_list = f"""
                    (
                        {class_filter_list}
                        OR (
                            u.origin = 'private'
                            AND (
                                EXISTS (
                                    SELECT 1
                                    FROM priv.spell_classes scp_filter_list
                                    WHERE scp_filter_list.spell_id = u.id
                                      AND scp_filter_list.class_code IN ({placeholders})
                                )
                            )
                        )
                    )
                """
            where.append(" ".join(class_filter_list.split()))
            params.extend(unique_codes)
            if private_attached:
                params.extend(unique_codes)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = conn.execute(
            f"""
            SELECT
                u.id,
                u.origin,
                u.spell_key,
                u.name_it,
                u.level,
                u.school,
                u.ritual,
                u.concentration,
                (
                    SELECT group_concat(DISTINCT x.class_code)
                    FROM (
                        SELECT scm.class_code AS class_code
                        FROM main.spell_classes scm
                        WHERE u.origin = 'srd' AND scm.spell_id = u.id
                        {("UNION SELECT scp.class_code AS class_code FROM priv.spell_classes scp WHERE u.origin = 'private' AND scp.spell_id = u.id")
                         if private_attached else ""}
                    ) x
                ) AS class_codes
            FROM ({union_sql}) u
            {where_sql}
            ORDER BY u.level ASC, u.name_it ASC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
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
                s.ritual,
                s.concentration,
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


def get_by_id(spell_id: int, origin: str = "srd", include_private: bool = False) -> dict | None:
    with connect() as conn:
        ensure_schema(conn)
        origin_norm = (origin or "srd").strip().lower()
        if origin_norm not in {"srd", "private"}:
            origin_norm = "srd"

        private_attached = False
        if include_private and PRIVATE_DB_PATH.exists():
            attached = {row[1] for row in conn.execute("PRAGMA database_list").fetchall()}
            if "priv" not in attached:
                conn.execute("ATTACH DATABASE ? AS priv", (str(PRIVATE_DB_PATH),))
            private_attached = True

        if origin_norm == "private":
            if not private_attached:
                return None
            table = "priv.spells"
            class_codes_sql = """
                (
                    SELECT group_concat(DISTINCT scp.class_code)
                    FROM priv.spell_classes scp
                    WHERE scp.spell_id = spells.id
                ) AS class_codes
            """
        else:
            table = "main.spells"
            class_codes_sql = """
                (
                    SELECT group_concat(DISTINCT sc.class_code)
                    FROM main.spell_classes sc
                    WHERE sc.spell_id = spells.id
                ) AS class_codes
            """

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
                """
            + class_codes_sql
            + f"""
            FROM {table} AS spells
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
        "origin": origin_norm,
        "spell_key": f"{origin_norm}:{int(row['id'])}",
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

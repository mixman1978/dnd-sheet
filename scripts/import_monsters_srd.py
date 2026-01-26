from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# Root del progetto (così trova "engine")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db import connect, ensure_schema

DATASET = Path("db/datasets/monsters_srd_it.json")


def parse_cr(value: Any) -> float:
    """Accetta CR come float/int o come stringa tipo '1/8'."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0.0
        if "/" in s:
            parts = s.split("/", 1)
            try:
                num = float(parts[0].strip())
                den = float(parts[1].strip())
                if den == 0:
                    return 0.0
                return num / den
            except ValueError:
                return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    return 0.0


def jdump(obj: Any) -> str | None:
    """Dump JSON per campi *_json. Se obj è None, ritorna None."""
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def upsert_monster(conn, m: dict) -> None:
    stats = m.get("stats")
    traits = m.get("traits")
    actions = m.get("actions")
    reactions = m.get("reactions")
    legendary_actions = m.get("legendary_actions")

    conn.execute(
        """
        INSERT INTO monsters(
            slug, name_it, cr, size, type, alignment,
            ac, hp, speed_text,
            senses_text, languages_text,
            stats_json, traits_json, actions_json, reactions_json, legendary_actions_json,
            description, source, updated_at
        )
        VALUES(
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, datetime('now')
        )
        ON CONFLICT(slug) DO UPDATE SET
            name_it=excluded.name_it,
            cr=excluded.cr,
            size=excluded.size,
            type=excluded.type,
            alignment=excluded.alignment,
            ac=excluded.ac,
            hp=excluded.hp,
            speed_text=excluded.speed_text,
            senses_text=excluded.senses_text,
            languages_text=excluded.languages_text,
            stats_json=excluded.stats_json,
            traits_json=excluded.traits_json,
            actions_json=excluded.actions_json,
            reactions_json=excluded.reactions_json,
            legendary_actions_json=excluded.legendary_actions_json,
            description=excluded.description,
            source=excluded.source,
            updated_at=datetime('now');
        """,
        (
            m["slug"],
            m["name_it"],
            parse_cr(m.get("cr")),
            m.get("size", "—"),
            m.get("type", "—"),
            m.get("alignment"),
            m.get("ac"),
            m.get("hp"),
            m.get("speed_text"),
            m.get("senses_text"),
            m.get("languages_text"),
            jdump(stats),
            jdump(traits),
            jdump(actions),
            jdump(reactions),
            jdump(legendary_actions),
            m.get("description"),
            m.get("source"),
        ),
    )


def main() -> None:
    if not DATASET.exists():
        raise SystemExit(f"Dataset non trovato: {DATASET}")

    monsters = json.loads(DATASET.read_text(encoding="utf-8"))
    if not isinstance(monsters, list):
        raise SystemExit("Dataset non valido: atteso array JSON")

    with connect() as conn:
        ensure_schema(conn)

        imported = 0
        skipped = 0

        for idx, m in enumerate(monsters, start=1):
            if not isinstance(m, dict):
                skipped += 1
                continue

            slug = (m.get("slug") or "").strip()
            name_it = (m.get("name_it") or "").strip()
            if not slug or not name_it:
                skipped += 1
                continue

            # campi minimi consigliati
            if not m.get("size") or not m.get("type") or m.get("cr") is None:
                # non blocchiamo: ma logghiamo come “soft warning”
                pass

            upsert_monster(conn, m)
            imported += 1

            # log leggero ogni 50 per dataset grandi
            if imported % 50 == 0:
                print(f"... importati {imported} mostri")

        conn.commit()

        total = conn.execute("SELECT COUNT(*) AS n FROM monsters;").fetchone()["n"]

    print(f"OK: importati/aggiornati {imported} mostri (saltati {skipped}).")
    print(f"DB: SELECT COUNT(*) FROM monsters => {total}")


if __name__ == "__main__":
    main()

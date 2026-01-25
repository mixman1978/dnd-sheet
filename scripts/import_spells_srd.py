from __future__ import annotations
import json,sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db import connect, ensure_schema

DATASET = Path("db/datasets/spells_srd_it.json")




# mapping class_code -> nome italiano (per tabella classes)
# (lo ampliamo dopo quando aggiungiamo PHB/Tasha/Xanathar extra)
CLASSES_IT = {
    "bard": "Bardo",
    "cleric": "Chierico",
    "druid": "Druido",
    "paladin": "Paladino",
    "ranger": "Ranger",
    "sorcerer": "Stregone",
    "warlock": "Warlock",
    "wizard": "Mago",
}

def upsert_class(conn, code: str, name_it: str) -> None:
    conn.execute(
        """
        INSERT INTO classes(code, name_it)
        VALUES(?, ?)
        ON CONFLICT(code) DO UPDATE SET name_it=excluded.name_it;
        """,
        (code, name_it),
    )

def upsert_spell(conn, s: dict) -> int:
    # Normalizza componenti
    comps = s.get("components") or {}
    v = 1 if comps.get("v") else 0
    ss = 1 if comps.get("s") else 0
    m = 1 if comps.get("m") else 0
    material_text = comps.get("material_text")

    conn.execute(
        """
        INSERT INTO spells(
            slug, name_it, level, school, casting_time, range_text,
            components_v, components_s, components_m, material_text,
            duration_text, concentration, ritual,
            description, at_higher_levels, source, updated_at
        )
        VALUES(
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, datetime('now')
        )
        ON CONFLICT(slug) DO UPDATE SET
            name_it=excluded.name_it,
            level=excluded.level,
            school=excluded.school,
            casting_time=excluded.casting_time,
            range_text=excluded.range_text,
            components_v=excluded.components_v,
            components_s=excluded.components_s,
            components_m=excluded.components_m,
            material_text=excluded.material_text,
            duration_text=excluded.duration_text,
            concentration=excluded.concentration,
            ritual=excluded.ritual,
            description=excluded.description,
            at_higher_levels=excluded.at_higher_levels,
            source=excluded.source,
            updated_at=datetime('now');
        """,
        (
            s["slug"],
            s["name_it"],
            int(s.get("level", 0)),
            s.get("school", "—"),
            s.get("casting_time", ""),
            s.get("range_text", ""),
            v,
            ss,
            m,
            material_text,
            s.get("duration_text", ""),
            1 if s.get("concentration") else 0,
            1 if s.get("ritual") else 0,
            s.get("description", ""),
            s.get("at_higher_levels"),
            s.get("source"),
        ),
    )

    # Recupera id spell
    cur = conn.execute("SELECT id FROM spells WHERE slug=?;", (s["slug"],))
    row = cur.fetchone()
    return int(row["id"])

def upsert_spell_classes(conn, spell_id: int, classes: list[str]) -> None:
    # Pulisce mapping esistente e reinserisce
    conn.execute("DELETE FROM spell_classes WHERE spell_id=?;", (spell_id,))
    for code in classes:
        conn.execute(
            "INSERT OR IGNORE INTO spell_classes(spell_id, class_code) VALUES(?, ?);",
            (spell_id, code),
        )

def main() -> None:
    if not DATASET.exists():
        raise SystemExit(f"Dataset non trovato: {DATASET}")

    spells = json.loads(DATASET.read_text(encoding="utf-8"))
    if not isinstance(spells, list):
        raise SystemExit("Dataset non valido: atteso array JSON")

    with connect() as conn:
        ensure_schema(conn)

        # Inserisci classi “note”
        for code, name_it in CLASSES_IT.items():
            upsert_class(conn, code, name_it)

        imported = 0
        for s in spells:
            if not isinstance(s, dict):
                continue
            if not s.get("slug") or not s.get("name_it"):
                continue

            spell_id = upsert_spell(conn, s)

            # mapping classi (se presente nel dataset)
            cls = s.get("classes") or []
            if isinstance(cls, list) and cls:
                upsert_spell_classes(conn, spell_id, [c for c in cls if isinstance(c, str)])

            imported += 1

        conn.commit()

    print(f"OK: importate/aggiornate {imported} spell nel DB.")

if __name__ == "__main__":
    main()

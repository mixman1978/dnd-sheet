from __future__ import annotations
import json,sys, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db import connect, ensure_schema

DATASET = Path("db/datasets/spells_srd_it.json")

SCHOOL_WORDS = [
    "Abiurazione",
    "Ammaliamento",
    "Divinazione",
    "Evocazione",
    "Illusione",
    "Invocazione",
    "Necromanzia",
    "Trasmutazione",
]

def make_description_cleaner(spells: list[dict]):
    """
    Rimuove code spurie del tipo:
      <Nome Incantesimo Successivo>\n<Scuola di X° livello ...>
    che a volte finiscono in coda alla descrizione per via dell’estrazione PDF.
    """
    names = []
    for s in spells:
        if isinstance(s, dict) and s.get("name_it"):
            names.append(str(s["name_it"]))

    # Evita match parziali: più lunghi prima
    uniq = sorted(set(names), key=len, reverse=True)
    if not uniq:
        return lambda txt: (txt, False)

    name_alt = "|".join(re.escape(n) for n in uniq)
    school_alt = "|".join(SCHOOL_WORDS)
    header_re = rf"(?:Trucchetto\s+di\s+[A-Za-zÀ-ÖØ-öø-ÿ]+|(?:{school_alt})\s+di\s+\d+°\s+livello(?:\s*\(rituale\))?)"

    tail_re = re.compile(
        rf"(?P<prefix>[\s\S]*?)(?:\n|\s)*(?P<name>(?:{name_alt}))\s*\n(?P<header>{header_re})\s*$",
        re.IGNORECASE,
    )
    tail_re2 = re.compile(
        rf"(?P<prefix>[\s\S]*?)[\.\!\?\…]\s*(?P<name>(?:{name_alt}))\s*\n(?P<header>{header_re})\s*$",
        re.IGNORECASE,
    )

    def clean(text: str):
        if not text:
            return text, False
        m = tail_re2.match(text) or tail_re.match(text)
        if not m:
            return text, False
        return m.group("prefix").rstrip(), True

    return clean



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
    clean_desc = make_description_cleaner(spells)
    fixed_desc = 0

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

            d = s.get("description", "")
            nd, changed = clean_desc(d if isinstance(d, str) else "")
            if changed:
                s["description"] = nd
                fixed_desc += 1

            spell_id = upsert_spell(conn, s)

            # mapping classi (se presente nel dataset)
            cls = s.get("classes") or []
            if isinstance(cls, list) and cls:
                upsert_spell_classes(conn, spell_id, [c for c in cls if isinstance(c, str)])

            imported += 1

        conn.commit()

    print(f"OK: importate/aggiornate {imported} spell nel DB. Descrizioni ripulite: {fixed_desc}.")


if __name__ == "__main__":
    main()

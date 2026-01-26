from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db import connect, ensure_schema


DEFAULT_DATASET = Path("db/datasets/classes_srd_it.json")


def _dumps(obj) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def upsert_class(conn, code: str, name_it: str) -> None:
    conn.execute(
        """
        INSERT INTO classes(code, name_it)
        VALUES(?, ?)
        ON CONFLICT(code) DO UPDATE SET name_it=excluded.name_it;
        """,
        (code, name_it),
    )


def upsert_class_details(conn, c: dict) -> None:
    sc = c.get("spellcasting") or {}
    conn.execute(
        """
        INSERT INTO class_details(
            class_code, hit_die,
            armor_proficiencies_json, weapon_proficiencies_json, tool_proficiencies_json,
            saving_throws_json, skill_choices_json, starting_equipment_json,
            spellcasting_ability, spellcasting_type,
            description, source
        )
        VALUES(
            ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?
        )
        ON CONFLICT(class_code) DO UPDATE SET
            hit_die=excluded.hit_die,
            armor_proficiencies_json=excluded.armor_proficiencies_json,
            weapon_proficiencies_json=excluded.weapon_proficiencies_json,
            tool_proficiencies_json=excluded.tool_proficiencies_json,
            saving_throws_json=excluded.saving_throws_json,
            skill_choices_json=excluded.skill_choices_json,
            starting_equipment_json=excluded.starting_equipment_json,
            spellcasting_ability=excluded.spellcasting_ability,
            spellcasting_type=excluded.spellcasting_type,
            description=excluded.description,
            source=excluded.source;
        """,
        (
            c["code"],
            int(c.get("hit_die") or 0),
            _dumps(c.get("armor_proficiencies")),
            _dumps(c.get("weapon_proficiencies")),
            _dumps(c.get("tool_proficiencies")),
            _dumps(c.get("saving_throws")),
            _dumps(c.get("skill_choices")),
            _dumps(c.get("starting_equipment")),
            sc.get("ability"),
            sc.get("type"),
            c.get("description"),
            c.get("source"),
        ),
    )


def replace_class_levels(conn, class_code: str, levels: list[dict]) -> None:
    conn.execute("DELETE FROM class_levels WHERE class_code=?;", (class_code,))
    for lv in levels:
        feats = lv.get("features") or []
        spell_slots_by_level = lv.get("spell_slots_by_level")
        conn.execute(
            """
            INSERT INTO class_levels(
                class_code, level, prof_bonus, features_json,
                cantrips_known, spells_known,
                spell_slots, slot_level,
                spell_slots_json,
                invocations_known
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                class_code,
                int(lv["level"]),
                int(lv.get("prof_bonus") or 0),
                _dumps(feats),
                lv.get("cantrips_known"),
                lv.get("spells_known"),
                lv.get("spell_slots"),
                lv.get("slot_level"),
                _dumps(spell_slots_by_level),
                lv.get("invocations_known"),
            ),
        )


def replace_class_features(conn, class_code: str, features: list[dict]) -> None:
    conn.execute("DELETE FROM class_features WHERE class_code=?;", (class_code,))
    for f in features:
        conn.execute(
            """
            INSERT INTO class_features(class_code, feature_key, level, name_it, description, source)
            VALUES(?, ?, ?, ?, ?, ?);
            """,
            (
                class_code,
                f["feature_key"],
                int(f.get("level") or 0),
                f.get("name_it") or f["feature_key"],
                f.get("description"),
                f.get("source"),
            ),
        )


def load_dataset(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Dataset non trovato: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Dataset non valido (atteso array JSON): {path}")
    return [x for x in data if isinstance(x, dict)]


def main() -> None:
    ap = argparse.ArgumentParser(description="Importa/aggiorna classi (SRD) nel DB.")
    ap.add_argument(
        "--in",
        dest="input",
        default=str(DEFAULT_DATASET),
        help=f"Percorso dataset JSON (default: {DEFAULT_DATASET})",
    )
    args = ap.parse_args()
    dataset_path = Path(args.input)

    classes = load_dataset(dataset_path)

    with connect() as conn:
        ensure_schema(conn)

        n = 0
        for c in classes:
            code = c.get("code")
            name_it = c.get("name_it")
            if not code or not name_it:
                continue

            upsert_class(conn, code, name_it)
            upsert_class_details(conn, c)
            replace_class_levels(conn, code, c.get("levels") or [])
            replace_class_features(conn, code, c.get("features") or [])
            n += 1

        conn.commit()

    print(f"OK: importate/aggiornate {n} classi da {dataset_path}.")


if __name__ == "__main__":
    main()

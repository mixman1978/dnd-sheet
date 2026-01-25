from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db import connect, ensure_schema

CLASSES_ALL = {
    "barbarian": "Barbaro",
    "bard": "Bardo",
    "cleric": "Chierico",
    "druid": "Druido",
    "fighter": "Guerriero",
    "monk": "Monaco",
    "paladin": "Paladino",
    "ranger": "Ranger",
    "rogue": "Ladro",
    "sorcerer": "Stregone",
    "warlock": "Warlock",
    "wizard": "Mago",
}

def main() -> None:
    with connect() as conn:
        ensure_schema(conn)
        for code, name_it in CLASSES_ALL.items():
            conn.execute(
                """
                INSERT INTO classes(code, name_it)
                VALUES(?, ?)
                ON CONFLICT(code) DO UPDATE SET name_it=excluded.name_it;
                """,
                (code, name_it),
            )
        conn.commit()
    print(f"OK: seed classes completato ({len(CLASSES_ALL)} classi).")

if __name__ == "__main__":
    main()

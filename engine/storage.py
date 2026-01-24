# engine/storage.py
import json
from pathlib import Path

DB_DIR = Path("db/characters")

def ensure_dirs():
    DB_DIR.mkdir(parents=True, exist_ok=True)

def list_characters() -> list[str]:
    ensure_dirs()
    return sorted([p.name for p in DB_DIR.glob("*.json")])

def save_character(name: str, pg: dict) -> str:
    ensure_dirs()
    safe = (name or "personaggio").strip().replace(" ", "_")
    path = DB_DIR / f"{safe}.json"
    path.write_text(json.dumps(pg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.name

def load_character(filename: str) -> dict:
    ensure_dirs()
    path = DB_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))

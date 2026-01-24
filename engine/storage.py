from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
CHAR_DIR = BASE_DIR / "db" / "characters"
CHAR_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    name = (name or "").strip() or "personaggio"
    name = re.sub(r"[^a-zA-Z0-9 _-]", "", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name.lower() or "personaggio"


def list_characters() -> List[str]:
    return sorted(p.stem for p in CHAR_DIR.glob("*.json"))


def load_character(slug: str) -> Dict[str, Any]:
    path = CHAR_DIR / f"{slug}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_character(data: Dict[str, Any]) -> str:
    nome = str(data.get("nome", "")).strip() or "Personaggio"
    slug = _slugify(nome)
    path = CHAR_DIR / f"{slug}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return slug

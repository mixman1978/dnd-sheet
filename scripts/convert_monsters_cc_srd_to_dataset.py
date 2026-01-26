from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

SRC_PATH = Path("db/datasets/sources/Monsters-SRD5.1-CCBY4.0License-TT.json")
OUT_PATH = Path("db/datasets/monsters_srd_it.json")
SRC_URL = "https://raw.githubusercontent.com/Tabyltop/CC-SRD/main/Monsters-SRD5.1-CCBY4.0License-TT.json"

SIZE_MAP = {
    "Tiny": "Minuscola",
    "Small": "Piccola",
    "Medium": "Media",
    "Large": "Grande",
    "Huge": "Enorme",
    "Gargantuan": "Mastodontica",
}

ALIGNMENT_MAP = {
    "unaligned": "non allineato",
    "any alignment": "qualsiasi allineamento",
    "lawful good": "legale buono",
    "lawful neutral": "legale neutrale",
    "lawful evil": "legale malvagio",
    "neutral good": "neutrale buono",
    "neutral": "neutrale",
    "neutral evil": "neutrale malvagio",
    "chaotic good": "caotico buono",
    "chaotic neutral": "caotico neutrale",
    "chaotic evil": "caotico malvagio",
}


def ensure_source_file() -> None:
    if SRC_PATH.exists():
        return
    SRC_PATH.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(SRC_URL) as response:
        SRC_PATH.write_bytes(response.read())


def slugify(value: str) -> str:
    s = (value or "").strip().lower()
    s = s.replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9\- ]+", "", s)
    s = re.sub(r"\\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def translate_size(value: Any) -> str:
    if not value:
        return ""
    s = str(value).strip()
    return SIZE_MAP.get(s, s)


def translate_alignment(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if v)
    s = str(value).strip().lower()
    return ALIGNMENT_MAP.get(s, str(value).strip())


def normalize_type(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        base = str(value.get("type") or "").strip()
        tags = value.get("tags")
        if isinstance(tags, list) and tags:
            tag_text = ", ".join(str(t) for t in tags if t)
            if tag_text:
                return f"{base} ({tag_text})".strip()
        return base
    return str(value).strip()


def first_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        m = re.search(r"\\d+", value)
        return int(m.group(0)) if m else None
    if isinstance(value, list):
        for item in value:
            found = first_int(item)
            if found is not None:
                return found
        return None
    if isinstance(value, dict):
        for key in ("value", "armor_class", "ac", "hit_points", "hp"):
            if key in value:
                found = first_int(value[key])
                if found is not None:
                    return found
        for item in value.values():
            found = first_int(item)
            if found is not None:
                return found
    return None


def normalize_speed(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if val is None:
                continue
            parts.append(f"{key} {val}")
        return ", ".join(parts)
    return str(value).strip()


def normalize_senses(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if val is None:
                continue
            parts.append(f"{key} {val}")
        return ", ".join(parts)
    return str(value).strip()


def normalize_languages(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value).strip()


def normalize_stats(value: Any) -> dict[str, int | None]:
    out = {"str": None, "dex": None, "con": None, "int": None, "wis": None, "cha": None}
    if not isinstance(value, dict):
        return out
    for key in out.keys():
        raw = value.get(key)
        if raw is None:
            continue
        try:
            out[key] = int(str(raw).strip())
        except ValueError:
            continue
    return out


def normalize_entries(value: Any) -> list[dict[str, str]]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        text = (item.get("description") or item.get("desc") or item.get("text") or "").strip()
        if not name and not text:
            continue
        out.append({"name": name, "text": text})
    return out


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if val is None:
                continue
            parts.append(f"{key} {val}")
        return ", ".join(parts)
    return str(value).strip()


def parse_cr(value: Any) -> str | float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return 0.0
    m = re.match(r"^([0-9]+\\s*/\\s*[0-9]+|[0-9]+(?:\\.[0-9]+)?)", s)
    if not m:
        return 0.0
    token = m.group(1).replace(" ", "")
    if "/" in token:
        return token
    try:
        return float(token)
    except ValueError:
        return 0.0


def monster_to_output(monster: dict[str, Any]) -> dict[str, Any]:
    name = (monster.get("name") or "").strip()
    traits = normalize_entries(monster.get("abilities") or monster.get("special_abilities"))

    extras = [
        ("Saving Throws", monster.get("saving_throws")),
        ("Skills", monster.get("skills")),
        ("Damage Vulnerabilities", monster.get("damage_vulnerabilities")),
        ("Damage Resistances", monster.get("damage_resistances")),
        ("Damage Immunities", monster.get("damage_immunities")),
        ("Condition Immunities", monster.get("condition_immunities")),
    ]
    for label, val in extras:
        text = to_text(val)
        if text:
            traits.append({"name": label, "text": text})

    return {
        "slug": slugify(name),
        "name_it": name,
        "cr": parse_cr(monster.get("challenge") or monster.get("cr") or monster.get("challenge_rating")),
        "size": translate_size(monster.get("size")),
        "type": normalize_type(monster.get("type")),
        "alignment": translate_alignment(monster.get("alignment")),
        "ac": first_int(monster.get("armor_class")),
        "hp": first_int(monster.get("hit_points")),
        "speed_text": normalize_speed(monster.get("speed")),
        "senses_text": normalize_senses(monster.get("senses")),
        "languages_text": normalize_languages(monster.get("languages")),
        "stats": normalize_stats(monster.get("stats")),
        "traits": traits,
        "actions": normalize_entries(monster.get("actions")),
        "reactions": normalize_entries(monster.get("reactions")),
        "legendary_actions": normalize_entries(monster.get("legendary_actions")),
        "description": "",
        "source": "SRD",
    }


def main() -> None:
    ensure_source_file()
    data = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    monsters = data.get("monsters") if isinstance(data, dict) else data
    if not isinstance(monsters, list):
        raise SystemExit("Dataset sorgente non valido: atteso array di mostri")

    out = [monster_to_output(m) for m in monsters if isinstance(m, dict)]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Letti: {len(monsters)} mostri")
    print(f"Scritti: {len(out)} mostri")
    print(f"OUT: {OUT_PATH}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from urllib.parse import urlsplit
from typing import Any
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from engine.characters import (
    delete_character as delete_character_in_db,
    get_character_id_by_name,
    list_characters,
    load_character as load_character_from_db,
    purge_characters as purge_characters_in_db,
    save_character as save_character_to_db,
)
from engine.db import connect, ensure_schema
from engine.rules import (
    STATS,
    STAT_LABEL,
    CLASSES,
    LINEAGES,
    LINEAGE_BONUS,
    ALIGNMENTS,
    SKILLS,
)
from engine.calc import (
    ability_mod,
    proficiency_bonus,
    total_stats,
    class_skill_choices,
    saving_throws,
    spellcasting_ability,
)
from engine.spellbook import (
    add_spell_to_character,
    list_character_spells,
    remove_spell_from_character,
)
from engine.spells_repo import get_by_id, search_spells

DEFAULT_PG = {
    "nome": "",
    "lineage": "Nessuno",
    "classe": "Guerriero",
    "level": 1,
    "alignment": "Neutrale",
    "stats_method": "manual",
    "stats_base": {"for": 10, "des": 10, "cos": 10, "int": 10, "sag": 10, "car": 10},
    "lineage_extra_stats": [None, None],  # solo Mezzelfo
    "skills_proficient": [],
    "hp_current": 0,
    "hp_temp": 0,
    # Combat basics (phase 2 foundation)
    "armor_type": "none",
    "has_shield": False,
    "ac_bonus": 0,
    "speed": 9,
    # Base attacks (no inventory yet)
    "atk_prof_melee": False,
    "atk_prof_ranged": False,
}

STANDARD_ARRAY_VALUES = [15, 14, 13, 12, 10, 8]
POINT_BUY_TOTAL = 27
POINT_BUY_COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}

# Defense proficiencies (minimal mapping)
ALLOWED_ARMOR_BY_CLASS = {
    "Mago": ["none"],
    "Chierico": ["none", "light", "medium"],
    "Bardo": ["none", "light"],
}

ALLOWED_SHIELD_BY_CLASS = {
    "Mago": False,
    "Chierico": True,
    "Bardo": False,
}

HIT_DIE_BY_CLASS = {
    "Barbaro": 12,
    "Guerriero": 10,
    "Paladino": 10,
    "Ranger": 10,
    "Bardo": 8,
    "Chierico": 8,
    "Druido": 8,
    "Monaco": 8,
    "Ladro": 8,
    "Warlock": 8,
    "Stregone": 6,
    "Mago": 6,
}

def new_pg() -> dict:
    return json.loads(json.dumps(DEFAULT_PG, ensure_ascii=False))


def clamp_int(v: Any, default: int, min_v: int | None = None, max_v: int | None = None) -> int:
    try:
        x = int(v)
    except Exception:
        x = default
    if min_v is not None:
        x = max(min_v, x)
    if max_v is not None:
        x = min(max_v, x)
    return x


def fmt_signed(n: Any) -> str:
    try:
        v = int(n)
    except Exception:
        return ""
    return f"+{v}" if v >= 0 else str(v)


def normalize_choice(v: Any, options: list[str], default: str) -> str:
    return v if isinstance(v, str) and v in options else default


def ensure_lineage_state(pg: dict) -> None:
    if not str(pg.get("lineage", "")).startswith("Mezzelfo"):
        pg["lineage_extra_stats"] = [None, None]
        return
    v = pg.get("lineage_extra_stats")
    if not isinstance(v, list):
        pg["lineage_extra_stats"] = [None, None]
    while len(pg["lineage_extra_stats"]) < 2:
        pg["lineage_extra_stats"].append(None)
    pg["lineage_extra_stats"] = pg["lineage_extra_stats"][:2]

    allowed = [s for s in STATS if s != "car"]
    pg["lineage_extra_stats"] = [x if x in allowed else None for x in pg["lineage_extra_stats"]]

    # no duplicati
    if pg["lineage_extra_stats"][0] and pg["lineage_extra_stats"][0] == pg["lineage_extra_stats"][1]:
        pg["lineage_extra_stats"][1] = None


def get_lineage_bonus(pg: dict) -> dict:
    base_bonus = dict(LINEAGE_BONUS.get(pg.get("lineage"), {}) or {})

    # Mezzelfo: aggiunge due +1 a scelta (non CAR)
    if str(pg.get("lineage", "")).startswith("Mezzelfo"):
        allowed = {s for s in STATS if s != "car"}
        seen = set()
        for st in (pg.get("lineage_extra_stats") or []):
            if st in allowed and st not in seen:
                base_bonus[st] = int(base_bonus.get(st, 0)) + 1
                seen.add(st)

    return base_bonus


def normalize_pg(pg: Any) -> dict:
    """Normalize an arbitrary PG payload to the shape expected by the UI."""
    pg = pg if isinstance(pg, dict) else new_pg()

    pg["lineage"] = normalize_choice(pg.get("lineage"), LINEAGES, "Nessuno")
    pg["classe"] = normalize_choice(pg.get("classe"), CLASSES, "Warlock")
    pg["alignment"] = normalize_choice(pg.get("alignment"), ALIGNMENTS, "Neutrale")
    pg["stats_method"] = normalize_choice(pg.get("stats_method"), ["manual", "standard", "point_buy"], "manual")
    pg["level"] = clamp_int(pg.get("level"), 1, 1, 20)

    if not isinstance(pg.get("stats_base"), dict):
        pg["stats_base"] = dict(DEFAULT_PG["stats_base"])
    for s in STATS:
        pg["stats_base"][s] = clamp_int(pg["stats_base"].get(s), 10, 1, 30)

    if not isinstance(pg.get("skills_proficient"), list):
        pg["skills_proficient"] = []

    pg["hp_current"] = clamp_int(pg.get("hp_current"), 0, 0, 999)
    pg["hp_temp"] = clamp_int(pg.get("hp_temp"), 0, 0, 999)
    pg["speed"] = clamp_int(pg.get("speed"), 9, 0, 60)
    armor_type = pg.get("armor_type")
    if armor_type not in ("none", "light", "medium", "heavy"):
        armor_type = "none"
    pg["armor_type"] = armor_type
    pg["has_shield"] = bool(pg.get("has_shield", False))
    pg["ac_bonus"] = clamp_int(pg.get("ac_bonus"), 0, -10, 10)
    pg["atk_prof_melee"] = bool(pg.get("atk_prof_melee", False))
    pg["atk_prof_ranged"] = bool(pg.get("atk_prof_ranged", False))

    ensure_lineage_state(pg)

    # Enforce armor/shield limits by class
    allowed_armor = ALLOWED_ARMOR_BY_CLASS.get(pg["classe"], ["none", "light", "medium", "heavy"])
    if pg["armor_type"] not in allowed_armor:
        pg["armor_type"] = "none"
    if not ALLOWED_SHIELD_BY_CLASS.get(pg["classe"], True):
        pg["has_shield"] = False
    recalc_spell_slots(pg)
    return pg


def standard_array_assignment(base_stats: dict) -> dict[str, int]:
    values = [int(base_stats.get(s, 0)) for s in STATS]
    if len(set(values)) == 6 and sorted(values) == sorted(STANDARD_ARRAY_VALUES):
        return {s: int(base_stats.get(s, 10)) for s in STATS}
    return {s: STANDARD_ARRAY_VALUES[idx] for idx, s in enumerate(STATS)}


def point_buy_assignment(base_stats: dict) -> dict[str, int]:
    assignment: dict[str, int] = {}
    for s in STATS:
        assignment[s] = clamp_int(base_stats.get(s), 8, 8, 15)
    return assignment


def point_buy_cost(stats: dict) -> int | None:
    total = 0
    for s in STATS:
        try:
            value = int(stats.get(s))
        except Exception:
            return None
        cost = POINT_BUY_COST.get(value)
        if cost is None:
            return None
        total += cost
    return total


def hp_max_average(level: int, con_mod: int, hit_die: int) -> int:
    if level <= 0:
        return 0
    first = hit_die + con_mod
    per_level = ((hit_die // 2) + 1) + con_mod
    return first + max(0, level - 1) * per_level


def build_sheet_context(pg: dict, allowed_skills: list[str] | None = None, choose_n: int = 0) -> dict:
    base_stats = pg.get("stats_base") if isinstance(pg.get("stats_base"), dict) else dict(DEFAULT_PG["stats_base"])
    lineage_bonus = get_lineage_bonus(pg)
    totals = total_stats(base_stats, lineage_bonus)
    mods = {s: ability_mod(int(totals.get(s, 10))) for s in STATS}
    pb = proficiency_bonus(pg.get("level") or 1)

    initiative = mods["des"]
    dex_mod = mods["des"]
    armor_type = pg.get("armor_type", "none")
    if armor_type == "medium":
        dex_to_ac = min(dex_mod, 2)
    elif armor_type == "heavy":
        dex_to_ac = 0
    else:
        dex_to_ac = dex_mod
    ac = 10 + dex_to_ac + (2 if pg.get("has_shield") else 0) + int(pg.get("ac_bonus", 0))

    st_prof = set(saving_throws(pg.get("classe")))
    saves: dict[str, int] = {}
    saving_rows = []
    for s in STATS:
        b = mods[s] + (pb if s in st_prof else 0)
        saves[s] = b
        saving_rows.append(
            {
                "stat": s,
                "label": STAT_LABEL[s],
                "bonus": b,
                "proficient": s in st_prof,
            }
        )

    con_mod = mods["cos"]
    class_name = pg.get("classe")
    class_hit_die = HIT_DIE_BY_CLASS.get(class_name) if isinstance(class_name, str) else None
    level = int(pg.get("level") or 1)
    hp_max_auto = hp_max_average(level, con_mod, class_hit_die) if class_hit_die else None

    allowed_armor = ALLOWED_ARMOR_BY_CLASS.get(pg.get("classe"), ["none", "light", "medium", "heavy"])
    shield_allowed = ALLOWED_SHIELD_BY_CLASS.get(pg.get("classe"), True)

    spell_ability = spellcasting_ability(pg.get("classe"))
    spell_mod = mods.get(spell_ability) if spell_ability else None
    spell_dc = (8 + pb + spell_mod) if spell_mod is not None else None
    spell_attack = (pb + spell_mod) if spell_mod is not None else None
    spellcasting = {
        "casting_ability": spell_ability,
        "ability": spell_ability,
        "ability_label": STAT_LABEL.get(spell_ability) if spell_ability else None,
        "mod": spell_mod,
        "spell_dc": spell_dc,
        "spell_attack_bonus": spell_attack,
        "dc": spell_dc,
        "attack_bonus": spell_attack,
    }

    prof_set = set(pg.get("skills_proficient") or [])
    all_skills = sorted(SKILLS.keys())
    skills: dict[str, int] = {}
    skill_rows = []
    allowed = allowed_skills or sorted(SKILLS.keys())
    for sk in all_skills:
        stat = SKILLS[sk]
        proficient = sk in prof_set
        bonus_val = mods[stat] + (pb if proficient else 0)
        skills[sk] = bonus_val
        skill_rows.append(
            {
                "name": sk,
                "stat": stat,
                "stat_label": STAT_LABEL[stat],
                "bonus": bonus_val,
                "proficient": proficient,
                "selectable": sk in allowed,
            }
        )

    perception_bonus = skills.get("Percezione", mods["sag"] + (pb if "Percezione" in prof_set else 0))
    skills["perception"] = perception_bonus
    passive_perception = 10 + skills["perception"]

    melee_attack_bonus = mods["for"] + (pb if pg.get("atk_prof_melee") else 0)
    ranged_attack_bonus = mods["des"] + (pb if pg.get("atk_prof_ranged") else 0)

    return {
        "base_stats": base_stats,
        "lineage_bonus": lineage_bonus,
        "totals": totals,
        "mods": mods,
        "prof_bonus": pb,
        "saves": saves,
        "skills": skills,
        "saving_rows": saving_rows,
        "skill_rows": skill_rows,
        "passive_perception": passive_perception,
        "spellcasting": spellcasting,
        "initiative": initiative,
        "ac": ac,
        "dex_mod": dex_mod,
        "hpmax": hp_max_auto,
        "hp": {
            "max_auto": hp_max_auto,
            "current": pg.get("hp_current", 0),
            "temp": pg.get("hp_temp", 0),
            "hit_die": class_hit_die,
            "con_mod": con_mod,
            "per_level_avg": ((class_hit_die // 2) + 1) if class_hit_die else None,
        },
        "melee_attack_bonus": melee_attack_bonus,
        "ranged_attack_bonus": ranged_attack_bonus,
        "allowed_armor": allowed_armor,
        "shield_allowed": shield_allowed,
        "choose_n": int(choose_n or 0),
        "allowed_skills": allowed,
        "speed_auto": 9,
        "hit_die": class_hit_die,
    }


def get_pg() -> dict:
    pg = session.get("pg")
    return normalize_pg(pg)


def save_pg(pg: dict) -> None:
    session["pg"] = pg


def _safe_filename_from_name(name: str | None) -> str:
    raw = (name or "personaggio").strip() or "personaggio"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw)
    return f"{safe[:60]}.json"


def _current_session_character_id() -> int | None:
    """Best-effort lookup of the DB id for the character currently in session."""
    pg = session.get("pg")
    if not isinstance(pg, dict):
        return None
    name = (pg.get("nome") or "").strip()
    if not name:
        return None
    try:
        return get_character_id_by_name(name)
    except Exception:
        return None


def _ensure_current_character_id() -> int:
    """Return current character id, creating/saving if needed."""
    pg = get_pg()
    name = (pg.get("nome") or "personaggio").strip() or "personaggio"
    char_id = _current_session_character_id()
    if char_id:
        return char_id
    try:
        return int(save_character_to_db(name, pg))
    except Exception:
        return 0


def _class_code_from_name_it(name_it: str | None) -> str | None:
    if not name_it:
        return None
    try:
        with connect() as conn:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT code FROM classes WHERE name_it = ?",
                ((name_it or "").strip(),),
            ).fetchone()
            if row and row[0]:
                return str(row[0])
    except Exception:
        return None
    return None


def _max_spell_level_for_class_level(class_code: str, level: int) -> int | None:
    code = (class_code or "").strip().lower()
    lv = clamp_int(level, 1, 1, 20)

    if code in {"bard", "cleric", "druid", "sorcerer", "wizard"}:
        if lv >= 17:
            return 9
        if lv >= 15:
            return 8
        if lv >= 13:
            return 7
        if lv >= 11:
            return 6
        if lv >= 9:
            return 5
        if lv >= 7:
            return 4
        if lv >= 5:
            return 3
        if lv >= 3:
            return 2
        return 1

    if code in {"paladin", "ranger"}:
        if lv >= 17:
            return 5
        if lv >= 13:
            return 4
        if lv >= 9:
            return 3
        if lv >= 5:
            return 2
        if lv >= 2:
            return 1
        return 0

    if code == "warlock":
        if lv >= 9:
            return 5
        if lv >= 7:
            return 4
        if lv >= 5:
            return 3
        if lv >= 3:
            return 2
        return 1

    return None


def _parse_bool_flag(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "on", "yes"}


FULL_CASTER_CODES = {"bard", "cleric", "druid", "sorcerer", "wizard"}
HALF_CASTER_CODES = {"paladin", "ranger"}
PREPARED_CASTER_ABILITY = {
    "cleric": "sag",
    "druid": "sag",
    "paladin": "car",
}

FULL_CASTER_SLOTS_BY_LEVEL: dict[int, dict[str, int]] = {
    1: {"1": 2},
    2: {"1": 3},
    3: {"1": 4, "2": 2},
    4: {"1": 4, "2": 3},
    5: {"1": 4, "2": 3, "3": 2},
    6: {"1": 4, "2": 3, "3": 3},
    7: {"1": 4, "2": 3, "3": 3, "4": 1},
    8: {"1": 4, "2": 3, "3": 3, "4": 2},
    9: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    10: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    11: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    12: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    13: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    14: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    15: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    16: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    17: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1, "9": 1},
    18: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 1, "7": 1, "8": 1, "9": 1},
    19: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 1, "8": 1, "9": 1},
    20: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 2, "8": 1, "9": 1},
}

HALF_CASTER_SINGLE_CLASS_SLOTS_BY_LEVEL: dict[int, dict[str, int]] = {
    1: {},
    2: {"1": 2},
    3: {"1": 3},
    4: {"1": 3},
    5: {"1": 4, "2": 2},
    6: {"1": 4, "2": 2},
    7: {"1": 4, "2": 3},
    8: {"1": 4, "2": 3},
    9: {"1": 4, "2": 3, "3": 2},
    10: {"1": 4, "2": 3, "3": 2},
    11: {"1": 4, "2": 3, "3": 3},
    12: {"1": 4, "2": 3, "3": 3},
    13: {"1": 4, "2": 3, "3": 3, "4": 1},
    14: {"1": 4, "2": 3, "3": 3, "4": 1},
    15: {"1": 4, "2": 3, "3": 3, "4": 2},
    16: {"1": 4, "2": 3, "3": 3, "4": 2},
    17: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    18: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    19: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    20: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
}

CLASS_CODE_ALIASES = {
    "bard": "bard",
    "bardo": "bard",
    "cleric": "cleric",
    "chierico": "cleric",
    "druid": "druid",
    "druido": "druid",
    "sorcerer": "sorcerer",
    "stregone": "sorcerer",
    "wizard": "wizard",
    "mago": "wizard",
    "warlock": "warlock",
    "paladin": "paladin",
    "paladino": "paladin",
    "ranger": "ranger",
}


def _empty_spell_slots_dict() -> dict[str, int]:
    return {str(i): 0 for i in range(1, 10)}


def _class_code_from_any(value: Any) -> str | None:
    raw = (value or "").strip().lower() if isinstance(value, str) else ""
    if not raw:
        return None
    alias = CLASS_CODE_ALIASES.get(raw)
    if alias:
        return alias
    if raw in FULL_CASTER_CODES or raw in HALF_CASTER_CODES or raw == "warlock":
        return raw
    db_code = _class_code_from_name_it(value if isinstance(value, str) else None)
    return (db_code or "").strip().lower() or None


def _extract_character_class_levels(character: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    explicit_found = False

    def add_entry(raw_code: Any, raw_level: Any) -> None:
        nonlocal explicit_found
        code = _class_code_from_any(raw_code)
        if not code:
            return
        level = clamp_int(raw_level, 0, 0, 20)
        if level <= 0:
            return
        explicit_found = True
        out[code] = int(out.get(code, 0)) + level

    data = character.get("classes")
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            add_entry(item.get("code") or item.get("class_code") or item.get("name_it") or item.get("classe"), item.get("level"))
    elif isinstance(data, dict):
        for key, value in data.items():
            add_entry(key, value)

    for key in ("multiclass", "spell_classes"):
        data = character.get(key)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    add_entry(
                        item.get("code") or item.get("class_code") or item.get("name_it") or item.get("classe") or item.get("class"),
                        item.get("level") or item.get("class_level") or item.get("lvl"),
                    )
        elif isinstance(data, dict):
            nested = data.get("classes")
            if isinstance(nested, list):
                for item in nested:
                    if not isinstance(item, dict):
                        continue
                    add_entry(
                        item.get("code") or item.get("class_code") or item.get("name_it") or item.get("classe") or item.get("class"),
                        item.get("level") or item.get("class_level") or item.get("lvl"),
                    )

    if not explicit_found:
        add_entry(character.get("classe"), character.get("level"))

    return out


def _warlock_slot_level(warlock_level: int) -> int:
    lv = clamp_int(warlock_level, 0, 0, 20)
    if lv <= 0:
        return 0
    if lv <= 2:
        return 1
    if lv <= 4:
        return 2
    if lv <= 6:
        return 3
    if lv <= 8:
        return 4
    return 5


def _warlock_slot_count(warlock_level: int) -> int:
    lv = clamp_int(warlock_level, 0, 0, 20)
    if lv <= 0:
        return 0
    if lv == 1:
        return 1
    if lv <= 10:
        return 2
    if lv <= 16:
        return 3
    return 4


def _get_slot_current(existing: dict, key: str, slot_max: int) -> int:
    raw = existing.get(key)
    if raw is None and key.isdigit():
        raw = existing.get(int(key))
    if raw is None:
        return 0
    return clamp_int(raw, 0, 0, slot_max)


def recalc_spell_slots(character: dict) -> dict:
    class_levels = _extract_character_class_levels(character)
    non_warlock_classes = [c for c, lv in class_levels.items() if lv > 0 and c != "warlock"]

    spell_slots_max = _empty_spell_slots_dict()
    if non_warlock_classes:
        if len(non_warlock_classes) == 1 and non_warlock_classes[0] in HALF_CASTER_CODES:
            class_level = clamp_int(class_levels[non_warlock_classes[0]], 0, 0, 20)
            single_half_slots = HALF_CASTER_SINGLE_CLASS_SLOTS_BY_LEVEL.get(class_level, {})
            for key, value in single_half_slots.items():
                spell_slots_max[key] = int(value)
        else:
            full_total = sum(class_levels.get(code, 0) for code in FULL_CASTER_CODES)
            half_total = sum(class_levels.get(code, 0) for code in HALF_CASTER_CODES)
            caster_level = clamp_int(full_total + (half_total // 2), 0, 0, 20)
            multiclass_slots = FULL_CASTER_SLOTS_BY_LEVEL.get(caster_level, {})
            for key, value in multiclass_slots.items():
                spell_slots_max[key] = int(value)

    existing_current = character.get("spell_slots_current")
    if isinstance(existing_current, dict):
        spell_slots_current = {
            key: _get_slot_current(existing_current, key, int(spell_slots_max[key])) for key in spell_slots_max
        }
    else:
        spell_slots_current = dict(spell_slots_max)

    warlock_level = clamp_int(class_levels.get("warlock", 0), 0, 0, 20)
    pact_slots_max = _warlock_slot_count(warlock_level)
    pact_slot_level = _warlock_slot_level(warlock_level)
    if "pact_slots_current" in character:
        pact_slots_current = clamp_int(character.get("pact_slots_current"), 0, 0, pact_slots_max)
    else:
        pact_slots_current = pact_slots_max

    character["spell_slots_max"] = spell_slots_max
    character["spell_slots_current"] = spell_slots_current
    character["pact_slot_level"] = pact_slot_level
    character["pact_slots_max"] = pact_slots_max
    character["pact_slots_current"] = pact_slots_current
    return character


def _safe_next_url(next_url: str | None) -> str:
    raw = (next_url or "").strip()
    if not raw:
        return url_for("index")
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return url_for("index")
    if not raw.startswith("/"):
        return url_for("index")
    return raw


def _persist_pg_to_session_and_db(pg: dict) -> int:
    recalc_spell_slots(pg)
    save_pg(pg)
    name = (pg.get("nome") or "personaggio").strip() or "personaggio"
    try:
        return int(save_character_to_db(name, pg))
    except Exception:
        return 0


def _build_spell_slots_view_model(pg: dict) -> dict:
    spell_slots_max = pg.get("spell_slots_max") if isinstance(pg.get("spell_slots_max"), dict) else {}
    spell_slots_current = pg.get("spell_slots_current") if isinstance(pg.get("spell_slots_current"), dict) else {}
    spell_slot_rows = []
    for lv in range(1, 10):
        key = str(lv)
        max_v = clamp_int(spell_slots_max.get(key, 0), 0, 0, 99)
        if max_v <= 0:
            continue
        cur_v = clamp_int(spell_slots_current.get(key, max_v), max_v, 0, max_v)
        spell_slot_rows.append({"level": lv, "current": cur_v, "max": max_v})

    pact_slots_max = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
    pact_slots_current = clamp_int(pg.get("pact_slots_current"), pact_slots_max, 0, pact_slots_max)
    pact_slot_level = clamp_int(pg.get("pact_slot_level"), 0, 0, 9)
    has_spell_slots_widget = bool(spell_slot_rows or pact_slots_max > 0)
    current_char_id = _current_session_character_id() or 0
    current_path = request.full_path[:-1] if request.full_path.endswith("?") else request.full_path

    return {
        "spell_slot_rows": spell_slot_rows,
        "pact_slots_max": pact_slots_max,
        "pact_slots_current": pact_slots_current,
        "pact_slot_level": pact_slot_level,
        "has_spell_slots_widget": has_spell_slots_widget,
        "current_char_id": current_char_id,
        "current_path": current_path,
    }


def _consume_spell_slot(pg: dict, spell_level: int) -> tuple[bool, str]:
    required_level = clamp_int(spell_level, 0, 0, 9)
    if required_level <= 0:
        return True, "trucchetto (nessuno slot consumato)"

    max_map = pg.get("spell_slots_max") if isinstance(pg.get("spell_slots_max"), dict) else {}
    cur_map = pg.get("spell_slots_current") if isinstance(pg.get("spell_slots_current"), dict) else {}
    for lv in range(required_level, 10):
        key = str(lv)
        max_v = clamp_int(max_map.get(key, 0), 0, 0, 99)
        if max_v <= 0:
            continue
        current = clamp_int(cur_map.get(key, max_v), max_v, 0, max_v)
        if current > 0:
            cur_map[key] = current - 1
            pg["spell_slots_current"] = cur_map
            return True, f"slot livello {lv} consumato"

    pact_max = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
    pact_current = clamp_int(pg.get("pact_slots_current"), pact_max, 0, pact_max)
    pact_slot_level = clamp_int(pg.get("pact_slot_level"), 0, 0, 9)
    if pact_max > 0 and pact_current > 0 and pact_slot_level >= required_level:
        pg["pact_slots_current"] = pact_current - 1
        return True, f"slot patto livello {pact_slot_level} consumato"

    return False, "nessuno slot disponibile"


def _available_cast_options_for_spell(pg: dict, spell_level: int) -> list[dict[str, str]]:
    level = clamp_int(spell_level, 0, 0, 9)
    if level <= 0:
        return [{"value": "cantrip", "label": "Trucchetto", "source": "cantrip"}]

    options: list[dict[str, str]] = []
    max_map = pg.get("spell_slots_max") if isinstance(pg.get("spell_slots_max"), dict) else {}
    cur_map = pg.get("spell_slots_current") if isinstance(pg.get("spell_slots_current"), dict) else {}
    for lv in range(level, 10):
        key = str(lv)
        max_v = clamp_int(max_map.get(key, 0), 0, 0, 99)
        if max_v <= 0:
            continue
        current = clamp_int(cur_map.get(key, max_v), max_v, 0, max_v)
        if current > 0:
            options.append({"value": f"standard:{lv}", "label": f"{lv}°", "source": "standard"})

    pact_max = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
    pact_current = clamp_int(pg.get("pact_slots_current"), pact_max, 0, pact_max)
    pact_slot_level = clamp_int(pg.get("pact_slot_level"), 0, 0, 9)
    if pact_max > 0 and pact_current > 0 and pact_slot_level >= level:
        options.append({"value": f"pact:{pact_slot_level}", "label": f"Patto {pact_slot_level}°", "source": "pact"})

    return options


def _available_cast_levels_for_spell(pg: dict, spell_level: int) -> list[dict[str, int | str]]:
    level = clamp_int(spell_level, 0, 0, 9)
    if level <= 0:
        return [{"level": 0, "remaining": 999, "value": "cantrip", "label": "Cantrip", "rest": "none"}]

    levels: list[dict[str, int | str]] = []
    max_map = pg.get("spell_slots_max") if isinstance(pg.get("spell_slots_max"), dict) else {}
    cur_map = pg.get("spell_slots_current") if isinstance(pg.get("spell_slots_current"), dict) else {}
    pact_max = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
    pact_current = clamp_int(pg.get("pact_slots_current"), pact_max, 0, pact_max)
    pact_slot_level = clamp_int(pg.get("pact_slot_level"), 0, 0, 9)

    for lv in range(level, 10):
        key = str(lv)
        max_v = clamp_int(max_map.get(key, 0), 0, 0, 99)
        if max_v > 0:
            current = clamp_int(cur_map.get(key, max_v), max_v, 0, max_v)
            levels.append(
                {"level": lv, "remaining": current, "value": f"standard:{lv}", "label": str(lv), "rest": "long"}
            )

    if pact_slot_level >= level and pact_max > 0:
        levels.append(
            {
                "level": pact_slot_level,
                "remaining": pact_current,
                "value": f"pact:{pact_slot_level}",
                "label": f"P{pact_slot_level}",
                "rest": "short",
            }
        )

    return levels


def _consume_spell_slot_by_choice(pg: dict, spell_level: int, cast_choice: str | None) -> tuple[bool, str]:
    level = clamp_int(spell_level, 0, 0, 9)
    if level <= 0:
        return True, "trucchetto (nessuno slot consumato)"

    raw = (cast_choice or "").strip().lower()
    if not raw:
        return _consume_spell_slot(pg, level)

    if raw.startswith("standard:"):
        chosen = clamp_int(raw.split(":", 1)[1], 0, 1, 9)
        if chosen < level:
            return False, "livello di lancio non valido"
        max_map = pg.get("spell_slots_max") if isinstance(pg.get("spell_slots_max"), dict) else {}
        cur_map = pg.get("spell_slots_current") if isinstance(pg.get("spell_slots_current"), dict) else {}
        key = str(chosen)
        max_v = clamp_int(max_map.get(key, 0), 0, 0, 99)
        if max_v <= 0:
            return False, "slot standard non disponibile"
        current = clamp_int(cur_map.get(key, max_v), max_v, 0, max_v)
        if current <= 0:
            return False, "slot standard esaurito"
        cur_map[key] = current - 1
        pg["spell_slots_current"] = cur_map
        return True, f"slot livello {chosen} consumato"

    if raw.startswith("pact:"):
        chosen = clamp_int(raw.split(":", 1)[1], 0, 1, 9)
        pact_max = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
        pact_current = clamp_int(pg.get("pact_slots_current"), pact_max, 0, pact_max)
        pact_slot_level = clamp_int(pg.get("pact_slot_level"), 0, 0, 9)
        if chosen and pact_slot_level != chosen:
            return False, "slot patto non disponibile a quel livello"
        if pact_slot_level < level:
            return False, "slot patto insufficiente"
        if pact_current <= 0:
            return False, "slot patto esaurito"
        pg["pact_slots_current"] = pact_current - 1
        return True, f"slot patto livello {pact_slot_level} consumato"

    return _consume_spell_slot(pg, level)


def _collect_pg_spellcasting_entries(pg: dict) -> list[tuple[str, int, str]]:
    entries: dict[str, tuple[int, str]] = {}

    def add_entry(code_raw: str | None, level_raw: Any, label_raw: str | None = None) -> None:
        code = (code_raw or "").strip().lower()
        if not code:
            return
        level = clamp_int(level_raw, 1, 1, 20)
        label = (label_raw or "").strip() or code
        prev = entries.get(code)
        if not prev or level > prev[0]:
            entries[code] = (level, label)

    main_label = (pg.get("classe") or "").strip()
    if main_label:
        add_entry(_class_code_from_name_it(main_label), pg.get("level"), main_label)

    for key in ("classes", "spell_classes", "multiclass"):
        data = pg.get(key)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    code = (item.get("class_code") or item.get("code") or "").strip().lower()
                    label = (
                        item.get("name_it")
                        or item.get("name")
                        or item.get("label")
                        or item.get("classe")
                        or item.get("class")
                    )
                    if not code and label:
                        code = (_class_code_from_name_it(str(label)) or "").strip().lower()
                    add_entry(code, item.get("class_level") or item.get("level") or item.get("lvl"), str(label or ""))
                elif isinstance(item, str):
                    code = item.strip().lower()
                    add_entry(code, pg.get("level"), code)
        elif isinstance(data, dict):
            nested_classes = data.get("classes")
            if isinstance(nested_classes, list):
                for item in nested_classes:
                    if not isinstance(item, dict):
                        continue
                    code = (item.get("class_code") or item.get("code") or "").strip().lower()
                    label = item.get("name_it") or item.get("name") or item.get("classe") or item.get("class")
                    if not code and label:
                        code = (_class_code_from_name_it(str(label)) or "").strip().lower()
                    add_entry(code, item.get("class_level") or item.get("level") or item.get("lvl"), str(label or ""))
            else:
                for maybe_code, maybe_level in data.items():
                    if isinstance(maybe_level, (int, str)):
                        add_entry(str(maybe_code), maybe_level, str(maybe_code))

    return [(code, lv, label) for code, (lv, label) in entries.items()]


def _compute_pg_spell_limits(pg: dict) -> tuple[set[str], int | None, list[str]]:
    entries = _collect_pg_spellcasting_entries(pg)
    allowed_codes: set[str] = {code for code, _, _ in entries if code}
    levels: list[int] = []
    labels: list[str] = []
    for class_code, class_level, label in entries:
        max_level = _max_spell_level_for_class_level(class_code, class_level)
        if max_level is not None:
            levels.append(max_level)
        if label and label not in labels:
            labels.append(label)

    return allowed_codes, (max(levels) if levels else None), labels


def _class_level_spell_limits(class_code: str, class_level: int) -> dict[str, int | None]:
    code = (class_code or "").strip().lower()
    lv = clamp_int(class_level, 1, 1, 20)
    out: dict[str, int | None] = {"max_spell_level": _max_spell_level_for_class_level(code, lv), "cantrips_known": None, "spells_known": None}
    try:
        with connect() as conn:
            ensure_schema(conn)
            row = conn.execute(
                """
                SELECT cantrips_known, spells_known
                FROM class_levels
                WHERE class_code = ? AND level = ?
                """,
                (code, lv),
            ).fetchone()
            if row:
                out["cantrips_known"] = int(row["cantrips_known"]) if row["cantrips_known"] is not None else None
                out["spells_known"] = int(row["spells_known"]) if row["spells_known"] is not None else None
    except Exception:
        pass
    return out


def _spell_class_codes(spell: dict) -> set[str]:
    raw = (spell.get("class_codes") or "").strip()
    if not raw:
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _owned_spells_for_class(owned: list[dict], class_code: str) -> list[dict]:
    code = (class_code or "").strip().lower()
    out = []
    for sp in owned:
        codes = _spell_class_codes(sp)
        if not codes or code in codes:
            out.append(sp)
    return out


def _can_add_spell_for_pg(pg: dict, owned: list[dict], spell: dict) -> tuple[bool, str]:
    spell_level = clamp_int(spell.get("level"), 0, 0, 9)
    spell_codes = _spell_class_codes(spell)
    class_levels = _extract_character_class_levels(pg)
    if not class_levels:
        return True, ""

    candidate_codes = [code for code, lv in class_levels.items() if lv > 0]
    if spell_codes:
        candidate_codes = [code for code in candidate_codes if code in spell_codes]
    if not candidate_codes:
        return False, "Incantesimo non compatibile con la/e classe/i del PG."

    reasons: list[str] = []
    for code in candidate_codes:
        lv = class_levels.get(code, 0)
        limits = _class_level_spell_limits(code, lv)
        max_spell_level = limits.get("max_spell_level")
        if spell_level > 0 and isinstance(max_spell_level, int) and spell_level > max_spell_level:
            reasons.append(f"{code}: livello incantesimo massimo {max_spell_level}")
            continue

        owned_for_code = _owned_spells_for_class(owned, code)
        if spell_level == 0:
            cantrips_known = limits.get("cantrips_known")
            if isinstance(cantrips_known, int):
                owned_cantrips = sum(1 for sp in owned_for_code if int(sp.get("level") or 0) == 0)
                if owned_cantrips >= cantrips_known:
                    reasons.append(f"{code}: limite trucchetti raggiunto ({cantrips_known})")
                    continue
        else:
            spells_known = limits.get("spells_known")
            if isinstance(spells_known, int):
                owned_spells = sum(1 for sp in owned_for_code if int(sp.get("level") or 0) > 0)
                if owned_spells >= spells_known:
                    reasons.append(f"{code}: limite incantesimi conosciuti raggiunto ({spells_known})")
                    continue
            else:
                prepared_ability = PREPARED_CASTER_ABILITY.get(code)
                if prepared_ability:
                    base_stats = pg.get("stats_base") if isinstance(pg.get("stats_base"), dict) else {}
                    totals = total_stats(base_stats, get_lineage_bonus(pg))
                    prepared_limit = max(1, lv + ability_mod(clamp_int(totals.get(prepared_ability), 10, 1, 30)))
                    owned_spells = sum(1 for sp in owned_for_code if int(sp.get("level") or 0) > 0)
                    if owned_spells >= prepared_limit:
                        reasons.append(f"{code}: limite incantesimi preparati raggiunto ({prepared_limit})")
                        continue

        return True, ""

    return False, "; ".join(reasons) if reasons else "Limiti di apprendimento superati."


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "dev-secret-key-change-me"

    # Garantisce che lo schema esista all'avvio.
    with connect() as conn:
        ensure_schema(conn)

    app.jinja_env.filters["fmt_signed"] = fmt_signed

    @app.route("/", methods=["GET", "POST"])
    def index():
        pg = get_pg()

        def _render_index(
            pg_view: dict,
            pb_assignment_override: dict[str, int] | None = None,
            persist_skill_cleanup: bool = True,
        ):
            standard_assignment = standard_array_assignment(pg_view["stats_base"])
            point_buy_values = pb_assignment_override or point_buy_assignment(pg_view["stats_base"])
            spent = point_buy_cost(point_buy_values)
            point_buy_spent = spent if spent is not None else 0
            point_buy_remaining = POINT_BUY_TOTAL - point_buy_spent

            sc = class_skill_choices(pg_view["classe"]) or {}
            choose_n = int(sc.get("choose") or 0)
            allowed_skills = sc.get("from") or sorted(SKILLS.keys())
            skills_filtered = [sk for sk in pg_view["skills_proficient"] if sk in allowed_skills]
            if choose_n > 0 and len(skills_filtered) > choose_n:
                skills_filtered = skills_filtered[:choose_n]
            if skills_filtered != pg_view["skills_proficient"]:
                pg_view["skills_proficient"] = skills_filtered
                if persist_skill_cleanup:
                    save_pg(pg_view)

            sheet = build_sheet_context(pg_view, allowed_skills=allowed_skills, choose_n=choose_n)
            mezzelfo_opts = [(s, STAT_LABEL[s]) for s in STATS if s != "car"]
            slots_vm = _build_spell_slots_view_model(pg_view)
            characters = list_characters()

            return render_template(
                "index.html",
                pg=pg_view,
                sheet=sheet,
                standard_array_values=STANDARD_ARRAY_VALUES,
                standard_assignment=standard_assignment,
                point_buy_values=sorted(POINT_BUY_COST.keys()),
                point_buy_assignment=point_buy_values,
                point_buy_total=POINT_BUY_TOTAL,
                point_buy_spent=point_buy_spent,
                point_buy_remaining=point_buy_remaining,
                mezzelfo_opts=mezzelfo_opts,
                characters=characters,
                spell_slot_rows=slots_vm["spell_slot_rows"],
                pact_slots_max=slots_vm["pact_slots_max"],
                pact_slots_current=slots_vm["pact_slots_current"],
                pact_slot_level=slots_vm["pact_slot_level"],
                has_spell_slots_widget=slots_vm["has_spell_slots_widget"],
                current_char_id=slots_vm["current_char_id"],
                current_path=slots_vm["current_path"],
                STATS=STATS,
                STAT_LABEL=STAT_LABEL,
                CLASSES=CLASSES,
                LINEAGES=LINEAGES,
                ALIGNMENTS=ALIGNMENTS,
            )

        if request.method == "POST":
            pg["nome"] = (request.form.get("nome") or pg.get("nome") or "personaggio").strip()
            pg["lineage"] = normalize_choice(request.form.get("lineage"), LINEAGES, pg["lineage"])
            pg["classe"] = normalize_choice(request.form.get("classe"), CLASSES, pg["classe"])
            pg["alignment"] = normalize_choice(request.form.get("alignment"), ALIGNMENTS, pg["alignment"])
            pg["stats_method"] = normalize_choice(
                request.form.get("stats_method"),
                ["manual", "standard", "point_buy"],
                pg["stats_method"],
            )
            pg["level"] = clamp_int(request.form.get("level"), pg["level"], 1, 20)

            if pg["stats_method"] == "standard":
                raw_standard = {s: request.form.get(f"std_stat_{s}") for s in STATS}
                # Transitional submit after method toggle: persist only the method, then render selects.
                if all(v in (None, "") for v in raw_standard.values()):
                    save_pg(pg)
                    return redirect(url_for("index"))

                selected_values = []
                parsed_stats: dict[str, int] = {}
                for s in STATS:
                    raw = raw_standard[s]
                    if raw is None or raw == "":
                        flash("Array standard non valido: assegna un valore a tutte le caratteristiche.", "danger")
                        return redirect(url_for("index"))
                    try:
                        value = int(raw)
                    except Exception:
                        flash("Array standard non valido: valori non numerici.", "danger")
                        return redirect(url_for("index"))
                    if value not in STANDARD_ARRAY_VALUES:
                        flash("Array standard non valido: usa solo 15,14,13,12,10,8.", "danger")
                        return redirect(url_for("index"))
                    parsed_stats[s] = value
                    selected_values.append(value)

                if len(set(selected_values)) != 6 or sorted(selected_values) != sorted(STANDARD_ARRAY_VALUES):
                    flash("Array standard non valido: ogni valore va usato una sola volta.", "danger")
                    return redirect(url_for("index"))

                for s in STATS:
                    pg["stats_base"][s] = parsed_stats[s]
            elif pg["stats_method"] == "point_buy":
                raw_point_buy = {s: request.form.get(f"pb_stat_{s}") for s in STATS}
                # Transitional submit after method toggle: persist only the method, then render selects.
                if all(v in (None, "") for v in raw_point_buy.values()):
                    save_pg(pg)
                    return redirect(url_for("index"))

                parsed_stats = point_buy_assignment(pg["stats_base"])
                for s in STATS:
                    raw = raw_point_buy[s]
                    if raw is None or raw == "":
                        flash("Point buy non valido: assegna un valore a tutte le caratteristiche.", "danger")
                        preview_pg = json.loads(json.dumps(pg, ensure_ascii=False))
                        preview_pg["stats_base"] = dict(parsed_stats)
                        return _render_index(preview_pg, pb_assignment_override=parsed_stats, persist_skill_cleanup=False)
                    try:
                        value = int(raw)
                    except Exception:
                        flash("Point buy non valido: valori non numerici.", "danger")
                        preview_pg = json.loads(json.dumps(pg, ensure_ascii=False))
                        preview_pg["stats_base"] = dict(parsed_stats)
                        return _render_index(preview_pg, pb_assignment_override=parsed_stats, persist_skill_cleanup=False)
                    if value < 8 or value > 15:
                        flash("Point buy non valido: ogni caratteristica deve essere tra 8 e 15.", "danger")
                        preview_pg = json.loads(json.dumps(pg, ensure_ascii=False))
                        preview_pg["stats_base"] = dict(parsed_stats)
                        return _render_index(preview_pg, pb_assignment_override=parsed_stats, persist_skill_cleanup=False)
                    parsed_stats[s] = value

                spent = point_buy_cost(parsed_stats)
                if spent is None:
                    flash("Point buy non valido: valori fuori tabella costi.", "danger")
                    preview_pg = json.loads(json.dumps(pg, ensure_ascii=False))
                    preview_pg["stats_base"] = dict(parsed_stats)
                    return _render_index(preview_pg, pb_assignment_override=parsed_stats, persist_skill_cleanup=False)
                if spent > POINT_BUY_TOTAL:
                    flash("Point buy non valido: superi 27 punti.", "danger")
                    preview_pg = json.loads(json.dumps(pg, ensure_ascii=False))
                    preview_pg["stats_base"] = dict(parsed_stats)
                    return _render_index(preview_pg, pb_assignment_override=parsed_stats, persist_skill_cleanup=False)

                for s in STATS:
                    pg["stats_base"][s] = parsed_stats[s]
            else:
                for s in STATS:
                    pg["stats_base"][s] = clamp_int(request.form.get(f"stat_{s}"), pg["stats_base"][s], 1, 30)

            pg["hp_current"] = clamp_int(request.form.get("hp_current"), pg.get("hp_current", 0), 0, 999)
            pg["hp_temp"] = clamp_int(request.form.get("hp_temp"), pg.get("hp_temp", 0), 0, 999)
            pg["speed"] = clamp_int(request.form.get("speed"), pg.get("speed", 9), 0, 60)
            armor_type = request.form.get("armor_type") or pg.get("armor_type") or "none"
            pg["armor_type"] = armor_type if armor_type in ("none", "light", "medium", "heavy") else "none"
            pg["has_shield"] = request.form.get("has_shield") is not None
            pg["ac_bonus"] = clamp_int(request.form.get("ac_bonus"), pg.get("ac_bonus", 0), -10, 10)
            pg["atk_prof_melee"] = request.form.get("atk_prof_melee") is not None
            pg["atk_prof_ranged"] = request.form.get("atk_prof_ranged") is not None

            # mezzelfo extras (se presenti)
            pg["lineage_extra_stats"] = [
                request.form.get("mezzelfo_0") or None,
                request.form.get("mezzelfo_1") or None,
            ]
            ensure_lineage_state(pg)

            sc = class_skill_choices(pg["classe"]) or {}
            choose_n = int(sc.get("choose") or 0)
            allowed_skills = sc.get("from") or sorted(SKILLS.keys())
            skills_selected = request.form.getlist("skills_proficient")
            skills_filtered = [sk for sk in skills_selected if sk in allowed_skills]
            if choose_n > 0 and len(skills_filtered) > choose_n:
                skills_filtered = skills_filtered[:choose_n]
            pg["skills_proficient"] = skills_filtered

            recalc_spell_slots(pg)
            save_pg(pg)
            return redirect(url_for("index"))
        return _render_index(pg)

    @app.post("/save_character")
    def save_character():
        pg = get_pg()
        name = (pg.get("nome") or "personaggio").strip() or "personaggio"
        recalc_spell_slots(pg)
        try:
            char_id = save_character_to_db(name, pg)
            flash(f"Salvato: {name} (#{char_id})", "success")
        except Exception:
            flash("Errore durante il salvataggio.", "danger")
        return redirect(url_for("index"))

    @app.post("/character/spell_slots/update")
    def update_spell_slots():
        pg = get_pg()
        session_char_id = _current_session_character_id() or 0
        form_char_id = clamp_int(request.form.get("character_id"), 0, 0, None)
        if form_char_id and session_char_id and form_char_id != session_char_id:
            flash("Personaggio corrente non coerente per aggiornamento slot.", "warning")
            return redirect(_safe_next_url(request.form.get("next")))

        slot_type = (request.form.get("slot_type") or "").strip().lower()
        delta = clamp_int(request.form.get("delta"), 0, -1, 1)
        if delta not in (-1, 1):
            return redirect(_safe_next_url(request.form.get("next")))

        if slot_type == "standard":
            slot_level = clamp_int(request.form.get("slot_level"), 0, 1, 9)
            if slot_level > 0:
                key = str(slot_level)
                max_map = pg.get("spell_slots_max") if isinstance(pg.get("spell_slots_max"), dict) else {}
                cur_map = pg.get("spell_slots_current") if isinstance(pg.get("spell_slots_current"), dict) else {}
                max_v = clamp_int(max_map.get(key, 0), 0, 0, 99)
                if max_v > 0:
                    current = clamp_int(cur_map.get(key, max_v), max_v, 0, max_v)
                    cur_map[key] = clamp_int(current + delta, current, 0, max_v)
                    pg["spell_slots_current"] = cur_map

        if slot_type == "pact":
            max_v = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
            current = clamp_int(pg.get("pact_slots_current"), max_v, 0, max_v)
            pg["pact_slots_current"] = clamp_int(current + delta, current, 0, max_v)

        _persist_pg_to_session_and_db(pg)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return ("", 204)
        return redirect(_safe_next_url(request.form.get("next")))

    @app.post("/character/spell_slots/rest")
    def rest_spell_slots():
        pg = get_pg()
        session_char_id = _current_session_character_id() or 0
        form_char_id = clamp_int(request.form.get("character_id"), 0, 0, None)
        if form_char_id and session_char_id and form_char_id != session_char_id:
            flash("Personaggio corrente non coerente per riposo.", "warning")
            return redirect(_safe_next_url(request.form.get("next")))

        rest_type = (request.form.get("rest_type") or "").strip().lower()
        if rest_type == "long":
            max_map = pg.get("spell_slots_max") if isinstance(pg.get("spell_slots_max"), dict) else {}
            pg["spell_slots_current"] = {
                str(i): clamp_int(max_map.get(str(i), 0), 0, 0, 99) for i in range(1, 10)
            }
            pact_max = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
            pg["pact_slots_current"] = pact_max
            _persist_pg_to_session_and_db(pg)
        elif rest_type == "short":
            pact_max = clamp_int(pg.get("pact_slots_max"), 0, 0, 99)
            pg["pact_slots_current"] = pact_max
            _persist_pg_to_session_and_db(pg)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return ("", 204)
        return redirect(_safe_next_url(request.form.get("next")))

    @app.get("/character/spell_slots/widget")
    def spell_slots_widget():
        pg = get_pg()
        return render_template("_spell_slots_widget.html", pg=pg, **_build_spell_slots_view_model(pg))

    @app.get("/load_character/<int:char_id>")
    def load_character(char_id: int):
        try:
            data = load_character_from_db(char_id)
        except Exception:
            data = None
        if not data:
            flash("Personaggio non trovato.", "warning")
            return redirect(url_for("index"))
        pg = normalize_pg(data)
        save_pg(pg)
        flash(f"Caricato: {pg.get('nome') or 'personaggio'}", "success")
        return redirect(url_for("index"))

    @app.post("/delete_character/<int:char_id>")
    def delete_character(char_id: int):
        session_char_id = _current_session_character_id()
        try:
            delete_character_in_db(char_id)
            if session_char_id == char_id:
                save_pg(new_pg())
            flash("Personaggio eliminato.", "success")
        except Exception:
            flash("Errore durante l'eliminazione.", "danger")
        return redirect(url_for("index"))

    @app.post("/purge_characters")
    def purge_characters():
        try:
            deleted = purge_characters_in_db()
            save_pg(new_pg())
            flash(f"Pulisci PG: {deleted} personaggi rimossi.", "warning")
        except Exception:
            flash("Errore durante la pulizia PG.", "danger")
        return redirect(url_for("index"))

    @app.get("/export_character")
    def export_character():
        pg = get_pg()
        payload = json.dumps(pg, ensure_ascii=False, indent=2)
        filename = _safe_filename_from_name(pg.get("nome"))
        headers = {"Content-Disposition": f"attachment; filename={filename}"}
        return Response(payload, mimetype="application/json; charset=utf-8", headers=headers)

    @app.post("/import_character")
    def import_character():
        file = request.files.get("character_file")
        if not file or not file.filename:
            flash("Seleziona un file JSON da importare.", "warning")
            return redirect(url_for("index"))

        try:
            raw = file.read()
            text = raw.decode("utf-8-sig", errors="strict")
            data = json.loads(text)
            pg = normalize_pg(data)
            save_pg(pg)
            flash(f"Import completato: {pg.get('nome') or 'personaggio'}", "success")
        except Exception:
            flash("JSON non valido: import annullato.", "danger")

        return redirect(url_for("index"))

    @app.get("/spells")
    def spells():
        pg = get_pg()
        # Non autosalvare il PG al semplice accesso della pagina Incantesimi.
        # Evita aggiornamenti involontari del record fallback "personaggio".
        character_id = _current_session_character_id()
        # Ordine alfabetico per label IT: Bardo, Chierico, Druido, Mago, Paladino, Ranger, Stregone, Warlock
        class_options = ["bard", "cleric", "druid", "wizard", "paladin", "ranger", "sorcerer", "warlock"]

        q = (request.args.get("q") or "").strip()
        level_raw = (request.args.get("level") or "").strip()
        class_code = (request.args.get("class_code") or "").strip().lower()
        ritual_only = (request.args.get("ritual_only") or "") == "1"
        concentration_only = (request.args.get("concentration_only") or "") == "1"
        include_private = (request.args.get("include_private") or "") == "1"
        pg_limits = _parse_bool_flag(request.args.get("pg_limits") or request.args.get("pg_mode"))
        page_raw = (request.args.get("page") or "1").strip()
        if class_code not in class_options:
            class_code = ""
        level = None
        if level_raw.isdigit():
            level = int(level_raw)
        page = int(page_raw) if page_raw.isdigit() and int(page_raw) > 0 else 1

        effective_class_code = class_code or None
        effective_class_codes = None
        pg_filter_max_spell_level = None
        pg_filter_class_label = None
        if pg_limits and character_id:
            allowed_class_codes, pg_filter_max_spell_level, pg_labels = _compute_pg_spell_limits(pg)
            if allowed_class_codes:
                effective_class_codes = sorted(allowed_class_codes)
            else:
                # PG presente ma classi non risolvibili: non mostrare risultati fuori limite.
                effective_class_code = "__no_class__"
            if pg_labels:
                pg_filter_class_label = ", ".join(pg_labels)

        has_filters = bool(q or level is not None or class_code or pg_limits or ritual_only or concentration_only)
        page_size = 30
        has_prev = page > 1
        has_next = False
        if has_filters:
            raw_results = search_spells(
                q=q,
                level=level,
                class_code=effective_class_code,
                class_codes=effective_class_codes,
                max_level=pg_filter_max_spell_level,
                ritual_only=ritual_only,
                concentration_only=concentration_only,
                include_private=include_private,
                limit=page_size + 1,
                offset=(page - 1) * page_size,
            )
            has_next = len(raw_results) > page_size
            results = raw_results[:page_size]
        else:
            results = []
        owned = list_character_spells(character_id) if character_id else []
        for sp in results:
            options = _available_cast_options_for_spell(pg, int(sp.get("level") or 0))
            sp["cast_options"] = options
            sp["can_cast"] = bool(options)
        for sp in owned:
            levels = _available_cast_levels_for_spell(pg, int(sp.get("level") or 0))
            sp["cast_levels"] = levels
            sp["can_cast"] = bool(levels)
        characters = list_characters()
        slots_vm = _build_spell_slots_view_model(pg)

        return render_template(
            "spells.html",
            pg=pg,
            q=q,
            level=level,
            class_code=class_code,
            class_options=class_options,
            ritual_only=ritual_only,
            concentration_only=concentration_only,
            include_private=include_private,
            pg_limits=pg_limits,
            pg_filter_class_label=pg_filter_class_label,
            pg_filter_max_spell_level=pg_filter_max_spell_level,
            page=page,
            has_prev=has_prev,
            has_next=has_next,
            results=results,
            owned=owned,
            characters=characters,
            **slots_vm,
        )

    @app.post("/spells/add")
    def spells_add():
        pg = get_pg()
        character_id = _ensure_current_character_id()
        spell_id = clamp_int(request.form.get("spell_id"), 0, 0, None)
        spell_origin = (request.form.get("spell_origin") or "srd").strip().lower()
        if character_id and spell_id:
            if spell_origin == "private":
                spell = get_by_id(spell_id, origin="private", include_private=True)
                if spell:
                    flash("Le spell private non possono essere aggiunte al personaggio nel DB SRD.", "warning")
                return redirect(
                    url_for(
                        "spells",
                        q=request.form.get("q") or "",
                        level=request.form.get("level") or "",
                        class_code=request.form.get("class_code") or "",
                        ritual_only=request.form.get("ritual_only") or "",
                        concentration_only=request.form.get("concentration_only") or "",
                        include_private=request.form.get("include_private") or "",
                        pg_limits=request.form.get("pg_limits") or request.form.get("pg_mode") or "",
                        page=request.form.get("page") or "1",
                    )
                )
            spell = get_by_id(spell_id, origin="srd")
            owned = list_character_spells(character_id)
            if any(int(sp.get("id") or 0) == spell_id for sp in owned):
                flash("Incantesimo gia' presente nel personaggio.", "warning")
            elif not spell:
                flash("Incantesimo non trovato.", "warning")
            else:
                allowed, reason = _can_add_spell_for_pg(pg, owned, spell)
                if allowed:
                    add_spell_to_character(character_id, spell_id)
                else:
                    flash(f"Aggiunta bloccata: {reason}", "warning")
        return redirect(
            url_for(
                "spells",
                q=request.form.get("q") or "",
                level=request.form.get("level") or "",
                class_code=request.form.get("class_code") or "",
                ritual_only=request.form.get("ritual_only") or "",
                concentration_only=request.form.get("concentration_only") or "",
                include_private=request.form.get("include_private") or "",
                pg_limits=request.form.get("pg_limits") or request.form.get("pg_mode") or "",
                page=request.form.get("page") or "1",
            )
        )

    @app.post("/spells/remove")
    def spells_remove():
        character_id = _ensure_current_character_id()
        spell_id = clamp_int(request.form.get("spell_id"), 0, 0, None)
        if character_id and spell_id:
            remove_spell_from_character(character_id, spell_id)
        return redirect(
            url_for(
                "spells",
                q=request.form.get("q") or "",
                level=request.form.get("level") or "",
                class_code=request.form.get("class_code") or "",
                ritual_only=request.form.get("ritual_only") or "",
                concentration_only=request.form.get("concentration_only") or "",
                include_private=request.form.get("include_private") or "",
                pg_limits=request.form.get("pg_limits") or request.form.get("pg_mode") or "",
                page=request.form.get("page") or "1",
            )
        )

    @app.post("/spells/cast")
    def spells_cast():
        pg = get_pg()
        spell_name = (request.form.get("spell_name") or "Incantesimo").strip()
        spell_level = clamp_int(request.form.get("spell_level"), 0, 0, 9)
        cast_choice = request.form.get("cast_choice")
        ok, detail = _consume_spell_slot_by_choice(pg, spell_level, cast_choice)
        if ok:
            _persist_pg_to_session_and_db(pg)
            flash(f"Lanciato: {spell_name} ({detail})", "success")
        else:
            flash(f"Impossibile lanciare {spell_name}: {detail}.", "warning")
        return redirect(
            url_for(
                "spells",
                q=request.form.get("q") or "",
                level=request.form.get("level") or "",
                class_code=request.form.get("class_code") or "",
                ritual_only=request.form.get("ritual_only") or "",
                concentration_only=request.form.get("concentration_only") or "",
                include_private=request.form.get("include_private") or "",
                pg_limits=request.form.get("pg_limits") or request.form.get("pg_mode") or "",
                page=request.form.get("page") or "1",
            )
        )

    @app.get("/spell/<int:spell_id>")
    def spell_detail(spell_id: int):
        origin = (request.args.get("origin") or "srd").strip().lower()
        include_private = origin == "private"
        spell = get_by_id(spell_id, origin=origin, include_private=include_private)
        if not spell:
            return ("Not found", 404)

        return render_template("spell_detail.html", spell=spell)

    @app.get("/spell/private/<int:spell_id>")
    def spell_detail_private(spell_id: int):
        spell = get_by_id(spell_id, origin="private", include_private=True)
        if not spell:
            return ("Not found", 404)
        return render_template("spell_detail.html", spell=spell)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8090, debug=True)

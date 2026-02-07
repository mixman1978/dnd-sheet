# engine/calc.py
from .rules import HIT_DIE_BY_CLASS, SPELLCASTING_ABILITY_BY_CLASS, SAVING_THROWS_BY_CLASS
from .db import connect, ensure_schema
import json

def ability_mod(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    return 2 + (max(1, int(level)) - 1) // 4


def mod(stat_total: int) -> int:
    return ability_mod(stat_total)


def prof_bonus(level: int) -> int:
    return proficiency_bonus(level)

def total_stats(base_stats: dict, lineage_bonus: dict) -> dict:
    out = {}
    for k, v in base_stats.items():
        out[k] = int(v) + int(lineage_bonus.get(k, 0))
    return out

def _normalize_class_name(classe) -> str:
    if isinstance(classe, dict):
        for key in ("name_it", "name", "label", "value", "nome", "classe"):
            val = classe.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        code = classe.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
        return ""
    if isinstance(classe, str):
        return classe
    if classe is None:
        return ""
    return str(classe)


def _class_code(classe) -> str | None:
    if isinstance(classe, dict):
        code = classe.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return None


def hit_die(classe: str) -> int:
    """Ritorna il dado vita della classe.

    Priorità:
    1) DB (class_details.hit_die) usando name_it (es: "Warlock")
    2) fallback su mapping hardcoded (engine.rules)
    """
    try:
        conn = connect()
        try:
            ensure_schema(conn)
            name = _normalize_class_name(classe)
            code = _class_code(classe)
            row = conn.execute(
                """
                SELECT cd.hit_die
                FROM classes c
                JOIN class_details cd ON cd.class_code = c.code
                WHERE c.name_it = ? OR c.code = ?
                """,
                (name, code or name),
            ).fetchone()
            if row and row[0] is not None:
                return int(row[0])
        finally:
            conn.close()
    except Exception:
        # DB non disponibile / schema non pronto: andiamo di fallback
        pass

    name = _normalize_class_name(classe)
    return HIT_DIE_BY_CLASS.get(name, 8)

def avg_roll(die: int) -> int:
    # media arrotondata per eccesso: es. d8 -> 5, d6 -> 4, d10 -> 6, d12 -> 7
    return (die // 2) + 1

def hp_max(level: int, classe: str, con_mod: int, method: str = "medio") -> int:
    d = hit_die(classe)
    if level <= 0:
        return 0
    if method == "medio":
        # livello 1: massimo dado
        # livelli successivi: media
        return d + con_mod + (level - 1) * (avg_roll(d) + con_mod)
    else:
        # per ora “tiro” non lo automatizziamo: lasciamo manuale più avanti
        return d + con_mod + (level - 1) * (avg_roll(d) + con_mod)

def spellcasting_ability(classe: str) -> str | None:
    name = _normalize_class_name(classe)
    return SPELLCASTING_ABILITY_BY_CLASS.get(name)

def saving_throws(classe: str) -> list[str]:
    """Ritorna la lista dei TS proficienti per la classe (es: ['sag','car']).

    Priorità:
    1) DB (class_details.saving_throws_json) usando classes.name_it (es: "Warlock")
    2) fallback su mapping hardcoded (engine.rules)
    """
    try:
        conn = connect()
        try:
            ensure_schema(conn)
            name = _normalize_class_name(classe)
            code = _class_code(classe)
            row = conn.execute(
                """
                SELECT cd.saving_throws_json
                FROM classes c
                JOIN class_details cd ON cd.class_code = c.code
                WHERE c.name_it = ? OR c.code = ?
                """,
                (name, code or name),
            ).fetchone()

            if row and row[0]:
                data = json.loads(row[0])
                if isinstance(data, list):
                    return [str(x) for x in data]
        finally:
            conn.close()
    except Exception:
        pass

    name = _normalize_class_name(classe)
    return SAVING_THROWS_BY_CLASS.get(name, [])

def class_skill_choices(classe: str) -> dict | None:
    """Ritorna le scelte abilità della classe, es:
    {"choose": 2, "from": ["Arcano", "Indagare", ...]}

    Priorità:
    1) DB (class_details.skill_choices_json) usando classes.name_it oppure classes.code
    2) None se non disponibile
    """
    try:
        conn = connect()
        try:
            ensure_schema(conn)
            name = _normalize_class_name(classe)
            code = _class_code(classe)
            row = conn.execute(
                """
                SELECT cd.skill_choices_json
                FROM classes c
                JOIN class_details cd ON cd.class_code = c.code
                WHERE c.name_it = ? OR c.code = ?
                """,
                (name, code or name),
            ).fetchone()

            if row and row[0]:
                data = json.loads(row[0])
                if isinstance(data, dict):
                    return data
        finally:
            conn.close()
    except Exception:
        pass

    return None

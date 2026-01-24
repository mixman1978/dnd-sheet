from __future__ import annotations
from typing import Dict

ABILITA_BY_STAT: Dict[str, list[str]] = {
    "for": ["Atletica"],
    "des": ["Acrobazia", "Furtività", "Rapidità di Mano"],
    "cos": [],
    "int": ["Arcano", "Indagare", "Natura", "Religione", "Storia"],
    "sag": ["Addestrare Animali", "Intuizione", "Medicina", "Percezione", "Sopravvivenza"],
    "car": ["Inganno", "Intimidire", "Intrattenere", "Persuasione"],
}

CARATTERISTICHE = ["for", "des", "cos", "int", "sag", "car"]
STATS_LABELS = {"for": "FOR", "des": "DES", "cos": "COS", "int": "INT", "sag": "SAG", "car": "CAR"}
SKILLS_BY_STAT = {
    "for": ["Atletica"],
    "des": ["Acrobazia", "Furtività", "Rapidità di Mano"],
    "int": ["Arcano", "Indagare", "Natura", "Religione", "Storia"],
    "sag": ["Addestrare Animali", "Intuizione", "Medicina", "Percezione", "Sopravvivenza"],
    "car": ["Inganno", "Intimidire", "Intrattenere", "Persuasione"],
}
SPELLCASTING_ABILITY_BY_CLASS = {
    "warlock": "car",
    "wizard": "int",
    "cleric": "sag",
    "druid": "sag",
    "paladin": "car",
    "ranger": "sag",
    "bard": "car",
    "sorcerer": "car",
}
CLASS_PRESETS_POINT_BUY = {
    "barbarian": {"for": 15, "des": 14, "cos": 15, "int": 8, "sag": 10, "car": 8},
    "bard": {"for": 8, "des": 14, "cos": 14, "int": 10, "sag": 10, "car": 15},
    "cleric": {"for": 14, "des": 8, "cos": 14, "int": 10, "sag": 15, "car": 10},
    "druid": {"for": 8, "des": 14, "cos": 14, "int": 10, "sag": 15, "car": 10},
    "fighter": {"for": 15, "des": 13, "cos": 15, "int": 8, "sag": 12, "car": 8},
    "rogue": {"for": 8, "des": 15, "cos": 14, "int": 10, "sag": 10, "car": 12},
    "wizard": {"for": 8, "des": 14, "cos": 14, "int": 15, "sag": 12, "car": 8},
    "monk": {"for": 10, "des": 15, "cos": 14, "int": 8, "sag": 15, "car": 8},
    "paladin": {"for": 15, "des": 8, "cos": 14, "int": 8, "sag": 10, "car": 15},
    "ranger": {"for": 10, "des": 15, "cos": 14, "int": 8, "sag": 14, "car": 10},
    "sorcerer": {"for": 8, "des": 14, "cos": 14, "int": 10, "sag": 10, "car": 15},
    "warlock": {"for": 8, "des": 14, "cos": 14, "int": 10, "sag": 10, "car": 15},
}
SAVING_THROW_PROF_BY_CLASS = {
    "barbarian": ["for", "cos"],
    "bard": ["des", "car"],
    "cleric": ["sag", "car"],
    "druid": ["int", "sag"],
    "fighter": ["for", "cos"],
    "rogue": ["des", "int"],
    "wizard": ["int", "sag"],
    "monk": ["for", "des"],
    "paladin": ["sag", "car"],
    "ranger": ["for", "des"],
    "sorcerer": ["cos", "car"],
    "warlock": ["sag", "car"],
}

def mod_caratteristica(score: int) -> int:
    # 5e: (score - 10) // 2 arrotondato per difetto
    return (int(score) - 10) // 2

def bonus_competenza(livello: int) -> int:
    # 5e: 1-4:+2, 5-8:+3, 9-12:+4, 13-16:+5, 17-20:+6
    lvl = max(1, min(20, int(livello)))
    if lvl <= 4:
        return 2
    if lvl <= 8:
        return 3
    if lvl <= 12:
        return 4
    if lvl <= 16:
        return 5
    return 6

def fmt_bonus(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


def total_stats(stats_base: dict, asi_bonus: dict) -> dict:
    return {k: int(stats_base.get(k, 0)) + int(asi_bonus.get(k, 0)) for k in CARATTERISTICHE}

# engine/calc.py
from .rules import HIT_DIE_BY_CLASS, SPELLCASTING_ABILITY_BY_CLASS

def mod(stat_total: int) -> int:
    return (stat_total - 10) // 2

def prof_bonus(level: int) -> int:
    # D&D 5e: 1-4 +2, 5-8 +3, 9-12 +4, 13-16 +5, 17-20 +6
    if level <= 4: return 2
    if level <= 8: return 3
    if level <= 12: return 4
    if level <= 16: return 5
    return 6

def total_stats(base_stats: dict, lineage_bonus: dict) -> dict:
    out = {}
    for k, v in base_stats.items():
        out[k] = int(v) + int(lineage_bonus.get(k, 0))
    return out

def hit_die(classe: str) -> int:
    return HIT_DIE_BY_CLASS.get(classe, 8)

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
    return SPELLCASTING_ABILITY_BY_CLASS.get(classe)

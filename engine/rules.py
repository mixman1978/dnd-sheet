# engine/rules.py

STATS = ["for", "des", "cos", "int", "sag", "car"]

STAT_LABEL = {
    "for": "FOR",
    "des": "DES",
    "cos": "COS",
    "int": "INT",
    "sag": "SAG",
    "car": "CAR",
}

ALIGNMENTS = [
    "Legale Buono","Neutrale Buono","Caotico Buono",
    "Legale Neutrale","Neutrale","Caotico Neutrale",
    "Legale Malvagio","Neutrale Malvagio","Caotico Malvagio",
]

CLASSES = [
    "Barbaro","Bardo","Chierico","Druido","Guerriero","Ladro",
    "Mago","Monaco","Paladino","Ranger","Stregone","Warlock",
]

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
    "Stregone": 6,
    "Warlock": 8,
    "Mago": 6,
}

# TS proficienti (stat) per classe
SAVING_THROWS_BY_CLASS = {
    "Barbaro": ["for", "cos"],
    "Bardo": ["des", "car"],
    "Chierico": ["cos", "sag"],
    "Druido": ["int", "sag"],
    "Guerriero": ["for", "cos"],
    "Ladro": ["des", "int"],
    "Mago": ["int", "sag"],
    "Monaco": ["for", "des"],
    "Paladino": ["sag", "car"],
    "Ranger": ["for", "des"],
    "Stregone": ["cos", "car"],
    "Warlock": ["sag", "car"],
}

# Abilità: nome -> stat
SKILLS = {
    "Acrobazia": "des",
    "Addestrare Animali": "sag",
    "Arcano": "int",
    "Atletica": "for",
    "Furtività": "des",
    "Indagare": "int",
    "Inganno": "car",
    "Intimidire": "car",
    "Intuizione": "sag",
    "Medicina": "sag",
    "Natura": "int",
    "Percezione": "sag",
    "Persuasione": "car",
    "Rapidità di Mano": "des",
    "Religione": "int",
    "Sopravvivenza": "sag",
    "Storia": "int",
    "Intrattenere": "car",
}

# Lineage: bonus (SRD classico)
LINEAGES = [
    "Nessuno",
    "Umano (+1 a tutto)",
    "Elfo (+2 DES)",
    "Nano (+2 COS)",
    "Halfling (+2 DES)",
    "Gnomo (+2 INT)",
    "Mezzelfo (+2 CAR, +1 due)",
    "Mezzorco (+2 FOR, +1 COS)",
    "Tiefling (+2 CAR, +1 INT)",
    "Dragonide (+2 FOR, +1 CAR)",
]

LINEAGE_BONUS = {
    "Nessuno": {},
    "Umano (+1 a tutto)": {"for": 1, "des": 1, "cos": 1, "int": 1, "sag": 1, "car": 1},
    "Elfo (+2 DES)": {"des": 2},
    "Nano (+2 COS)": {"cos": 2},
    "Halfling (+2 DES)": {"des": 2},
    "Gnomo (+2 INT)": {"int": 2},
    # Mezzelfo: base +2 CAR, i due +1 li gestiamo in main.py
    "Mezzelfo (+2 CAR, +1 due)": {"car": 2},
    "Mezzorco (+2 FOR, +1 COS)": {"for": 2, "cos": 1},
    "Tiefling (+2 CAR, +1 INT)": {"car": 2, "int": 1},
    "Dragonide (+2 FOR, +1 CAR)": {"for": 2, "car": 1},
}


SPELLCASTING_ABILITY_BY_CLASS = {
    "Bardo": "car",
    "Chierico": "sag",
    "Druido": "sag",
    "Mago": "int",
    "Paladino": "car",
    "Ranger": "sag",
    "Stregone": "car",
    "Warlock": "car",
}

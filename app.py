import json
import streamlit as st
from engine.rules import (
    CARATTERISTICHE,
    CLASS_PRESETS_POINT_BUY,
    SAVING_THROW_PROF_BY_CLASS,
    SKILLS_BY_STAT,
    SPELLCASTING_ABILITY_BY_CLASS,
    STATS_LABELS,
    bonus_competenza,
    fmt_bonus,
    mod_caratteristica,
    total_stats,
)
from engine.storage import list_characters, load_character, save_character


st.set_page_config(page_title="DnD Sheet", page_icon="🎲", layout="wide", initial_sidebar_state="expanded")


def inject_compact_css():
    st.markdown(
        """
        <style>
        /* Container generale */
        .block-container {
            padding-top: 0.6rem !important;
            padding-bottom: 0.6rem !important;
            max-width: 1200px !important; /* alza/abbassa a gusto */
        }

        /* Sidebar più stretta e compatta */
        [data-testid="stSidebar"] { width: 260px !important; }
        [data-testid="stSidebarContent"] {
            padding-top: 0.6rem !important;
            padding-bottom: 0.6rem !important;
        }

        /* Riduci spazi tra blocchi */
        [data-testid="stVerticalBlock"] { gap: 0.35rem !important; }
        [data-testid="stHorizontalBlock"] { gap: 0.6rem !important; }

        /* Titoli più stretti */
        h1 { margin: 0.2rem 0 0.4rem 0 !important; }
        h2 { margin: 0.2rem 0 0.4rem 0 !important; }
        h3 { margin: 0.2rem 0 0.35rem 0 !important; }
        p  { margin: 0.15rem 0 !important; }

        /* Label dei widget */
        label { margin-bottom: 0.05rem !important; }

        /* Input: riduci altezza (funziona bene su number_input/text_input/selectbox) */
        div[data-baseweb="input"] input {
            height: 32px !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        div[data-baseweb="select"] > div {
            min-height: 32px !important;
        }

        /* Metric più compatte */
        [data-testid="stMetric"] { padding: 0.25rem 0.25rem !important; }
        [data-testid="stMetricValue"] { font-size: 1.35rem !important; }

        /* Tabs più compatti */
        button[role="tab"] { padding: 0.25rem 0.6rem !important; }

        /* Topbar sticky */
        .topbar {
            position: sticky;
            top: 0;
            z-index: 999;
            background: rgba(255, 255, 255, 0.95);
            border-bottom: 1px solid #eee;
            padding: 0.35rem 0.25rem;
            margin-bottom: 0.6rem;
            backdrop-filter: blur(6px);
        }
        .topbar-inner { max-width: 1200px; margin: 0 auto; }

        /* Nascondi “decorazioni” Streamlit */
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )



inject_compact_css()

# Classi: IT, ma Warlock resta "Warlock"
CLASSI = {
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

LABELS = list(CLASSI.values())
LABEL_TO_SLUG = {v: k for k, v in CLASSI.items()}
STAT_LABEL_TO_KEY = {v: k for k, v in STATS_LABELS.items()}
ALIGNMENTS = [
    "Legale Buono",
    "Neutrale Buono",
    "Caotico Buono",
    "Legale Neutrale",
    "Neutrale",
    "Caotico Neutrale",
    "Legale Malvagio",
    "Neutrale Malvagio",
    "Caotico Malvagio",
]

# Migrazione eventuale (se in vecchi JSON avevi "Warlock" ecc.)
LEGACY = {
    "Warlock": "warlock",
    "Wizard": "wizard",
    "Cleric": "cleric",
    "Fighter": "fighter",
}


def hit_die_max(hit_die_type: str) -> int:
    try:
        return int(str(hit_die_type).lstrip("d"))
    except ValueError:
        return 8


def hit_die_avg(hit_die_type: str) -> int:
    averages = {"d6": 4, "d8": 5, "d10": 6, "d12": 7}
    return averages.get(str(hit_die_type), 5)


def sync_widgets_from_pg(force: bool = False) -> None:
    pg = st.session_state.pg
    if "stats_base" not in pg:
        if "stats" in pg:
            pg["stats_base"] = {k: int(pg["stats"].get(k, 10)) for k in CARATTERISTICHE}
        else:
            pg["stats_base"] = {k: 10 for k in CARATTERISTICHE}
    if "asi_bonus" not in pg:
        pg["asi_bonus"] = {k: 0 for k in CARATTERISTICHE}
    if "lineage" not in pg:
        pg["lineage"] = "none"
    if "saving_throws_proficient" not in pg:
        pg["saving_throws_proficient"] = {k: False for k in CARATTERISTICHE}
    if "saving_throws_auto" not in pg:
        pg["saving_throws_auto"] = True
    if "skills" not in pg:
        pg["skills"] = {
            skill: {"proficient": False, "expertise": False}
            for skills in SKILLS_BY_STAT.values()
            for skill in skills
        }
    if "hp_max" not in pg:
        pg["hp_max"] = 1
    if "hp_current" not in pg:
        pg["hp_current"] = int(pg.get("hp_max", 1))
    if "hp_temp" not in pg:
        pg["hp_temp"] = 0
    if "ac_base" not in pg:
        pg["ac_base"] = 10
    if "ac_bonus" not in pg:
        pg["ac_bonus"] = 0
    if "iniziativa_bonus" not in pg:
        pg["iniziativa_bonus"] = 0
    if "speed_walk" not in pg:
        pg["speed_walk"] = 9
    if "hit_die_type" not in pg:
        pg["hit_die_type"] = "d8"
    if "hit_dice_total" not in pg:
        pg["hit_dice_total"] = 1
    if "hit_dice_remaining" not in pg:
        pg["hit_dice_remaining"] = int(pg.get("hit_dice_total", 1))
    if "level" not in pg:
        if "livello" in pg:
            pg["level"] = int(pg.get("livello", 1) or 1)
        else:
            pg["level"] = 1
    else:
        pg["level"] = int(pg.get("level", 1) or 1)
    if "alignment" not in pg:
        pg["alignment"] = "Neutrale"
    if "hp_method" not in pg:
        pg["hp_method"] = "Medio"
    if "hp_rolls" not in pg:
        pg["hp_rolls"] = ""
    if "hp_first_level" not in pg:
        pg["hp_first_level"] = hit_die_max(pg.get("hit_die_type", "d8"))
    level_for_total = int(st.session_state.get("ui_level", pg["level"]))
    pg["level"] = level_for_total
    old_total = int(pg.get("hit_dice_total", level_for_total))
    ui_remaining = st.session_state.get("ui_hit_dice_remaining")
    if ui_remaining is None or force:
        old_remaining = int(pg.get("hit_dice_remaining", old_total))
    else:
        old_remaining = int(ui_remaining)
    new_total = level_for_total
    if old_remaining == old_total:
        new_remaining = new_total
    else:
        new_remaining = max(0, min(old_remaining, new_total))
    pg["hit_dice_total"] = new_total
    pg["hit_dice_remaining"] = new_remaining
    if force or "ui_nome" not in st.session_state:
        st.session_state["ui_nome"] = str(pg.get("nome", ""))
    if force or "ui_classe_label" not in st.session_state:
        slug = pg.get("classe", "warlock")
        st.session_state["ui_classe_label"] = CLASSI.get(slug, "Warlock")
    for key in CARATTERISTICHE:
        widget_key = f"stats_base_{key}"
        if force or widget_key not in st.session_state:
            st.session_state[widget_key] = int(pg["stats_base"].get(key, 10))
        st_key = f"st_prof_{key}"
        if force or st_key not in st.session_state:
            st.session_state[st_key] = bool(pg["saving_throws_proficient"].get(key, False))
    for skills in SKILLS_BY_STAT.values():
        for skill in skills:
            entry = pg["skills"].setdefault(skill, {"proficient": False, "expertise": False})
            prof_key = f"sk_prof_{skill}"
            exp_key = f"sk_exp_{skill}"
            prof = bool(entry.get("proficient", False))
            exp = bool(entry.get("expertise", False))
            if not prof:
                exp = False
                entry["expertise"] = False
            if force or prof_key not in st.session_state:
                st.session_state[prof_key] = prof
            if force or exp_key not in st.session_state:
                st.session_state[exp_key] = exp
    if force or "ui_lineage" not in st.session_state:
        lineage_label = {
            "none": "Nessuno",
            "human": "Umano (+1 a tutto)",
            "vhuman": "Umano Variante (+1 +1)",
            "custom_2_1": "Personalizzato (+2/+1)",
        }.get(pg.get("lineage", "none"), "Nessuno")
        st.session_state["ui_lineage"] = lineage_label
    if force or "ui_alignment" not in st.session_state:
        st.session_state["ui_alignment"] = str(pg.get("alignment", "Neutrale"))
    if force or "ui_vhuman_a" not in st.session_state or "ui_vhuman_b" not in st.session_state:
        vhuman_stats = [k for k, v in pg["asi_bonus"].items() if int(v) == 1]
        a = vhuman_stats[0] if len(vhuman_stats) > 0 else "for"
        b = vhuman_stats[1] if len(vhuman_stats) > 1 else "des"
        if a == b:
            b = "des" if a != "des" else "for"
        st.session_state["ui_vhuman_a"] = STATS_LABELS.get(a, a.upper())
        st.session_state["ui_vhuman_b"] = STATS_LABELS.get(b, b.upper())
    if force or "ui_custom_plus2" not in st.session_state or "ui_custom_plus1" not in st.session_state:
        plus2 = next((k for k, v in pg["asi_bonus"].items() if int(v) == 2), "for")
        plus1 = next((k for k, v in pg["asi_bonus"].items() if int(v) == 1), "des")
        if plus2 == plus1:
            plus1 = "des" if plus2 != "des" else "for"
        st.session_state["ui_custom_plus2"] = STATS_LABELS.get(plus2, plus2.upper())
        st.session_state["ui_custom_plus1"] = STATS_LABELS.get(plus1, plus1.upper())
    if force or "ui_hp_max" not in st.session_state:
        st.session_state["ui_hp_max"] = int(pg.get("hp_max", 1))
    if force or "ui_hp_current" not in st.session_state:
        st.session_state["ui_hp_current"] = int(pg.get("hp_current", pg.get("hp_max", 1)))
    if force or "ui_hp_temp" not in st.session_state:
        st.session_state["ui_hp_temp"] = int(pg.get("hp_temp", 0))
    if force or "ui_ac_base" not in st.session_state:
        st.session_state["ui_ac_base"] = int(pg.get("ac_base", 10))
    if force or "ui_ac_bonus" not in st.session_state:
        st.session_state["ui_ac_bonus"] = int(pg.get("ac_bonus", 0))
    if force or "ui_init_bonus" not in st.session_state:
        st.session_state["ui_init_bonus"] = int(pg.get("iniziativa_bonus", 0))
    if force or "ui_speed_walk" not in st.session_state:
        st.session_state["ui_speed_walk"] = int(pg.get("speed_walk", 9))
    if force or "ui_hit_die_type" not in st.session_state:
        hit_die_type = str(pg.get("hit_die_type", "d8"))
        if hit_die_type not in ["d6", "d8", "d10", "d12"]:
            hit_die_type = "d8"
        st.session_state["ui_hit_die_type"] = hit_die_type
    if force or "ui_hit_dice_remaining" not in st.session_state:
        st.session_state["ui_hit_dice_remaining"] = int(pg.get("hit_dice_remaining", 1))
    else:
        current_remaining = int(st.session_state.get("ui_hit_dice_remaining", 0))
        if current_remaining != int(pg.get("hit_dice_remaining", 1)):
            st.session_state["ui_hit_dice_remaining"] = int(pg.get("hit_dice_remaining", 1))
    if force or "ui_level" not in st.session_state:
        st.session_state["ui_level"] = int(pg.get("level", 1))
    if force or "ui_hp_method" not in st.session_state:
        st.session_state["ui_hp_method"] = str(pg.get("hp_method", "Medio"))
    if force or "ui_hp_rolls" not in st.session_state:
        st.session_state["ui_hp_rolls"] = str(pg.get("hp_rolls", ""))
    if force or "ui_hp_first_level" not in st.session_state:
        st.session_state["ui_hp_first_level"] = int(
            pg.get("hp_first_level", hit_die_max(pg.get("hit_die_type", "d8")))
        )


def _on_skill_prof_change(skill: str) -> None:
    if not st.session_state.get(f"sk_prof_{skill}", False):
        st.session_state[f"sk_exp_{skill}"] = False


def _on_saving_throw_change(stat_key: str) -> None:
    pg = st.session_state.pg
    pg["saving_throws_auto"] = False
    pg.setdefault("saving_throws_proficient", {})
    pg["saving_throws_proficient"][stat_key] = bool(st.session_state.get(f"st_prof_{stat_key}", False))

# Stato iniziale
if "pg" not in st.session_state:
    st.session_state.pg = {
        "nome": "Azir",
        "classe": "warlock",
        "stats_base": {"for": 10, "des": 10, "cos": 10, "int": 10, "sag": 10, "car": 10},
        "asi_bonus": {"for": 0, "des": 0, "cos": 0, "int": 0, "sag": 0, "car": 0},
        "lineage": "none",
        "hp_max": 1,
        "hp_current": 1,
        "hp_temp": 0,
        "ac_base": 10,
        "ac_bonus": 0,
        "iniziativa_bonus": 0,
        "speed_walk": 9,
        "hit_die_type": "d8",
        "hit_dice_total": 1,
        "hit_dice_remaining": 1,
        "level": 1,
        "hp_method": "Medio",
        "hp_rolls": "",
        "hp_first_level": hit_die_max("d8"),
        "alignment": "Neutrale",
    }
if "current_slug" not in st.session_state:
    st.session_state.current_slug = None
if "stats_base" not in st.session_state.pg:
    if "stats" in st.session_state.pg:
        st.session_state.pg["stats_base"] = {
            k: int(st.session_state.pg["stats"].get(k, 10)) for k in CARATTERISTICHE
        }
    else:
        st.session_state.pg["stats_base"] = {k: 10 for k in CARATTERISTICHE}
if "asi_bonus" not in st.session_state.pg:
    st.session_state.pg["asi_bonus"] = {k: 0 for k in CARATTERISTICHE}
if "lineage" not in st.session_state.pg:
    st.session_state.pg["lineage"] = "none"
if "saving_throws_proficient" not in st.session_state.pg:
    st.session_state.pg["saving_throws_proficient"] = {k: False for k in CARATTERISTICHE}
if "saving_throws_auto" not in st.session_state.pg:
    st.session_state.pg["saving_throws_auto"] = True
if "skills" not in st.session_state.pg:
    st.session_state.pg["skills"] = {
        skill: {"proficient": False, "expertise": False}
        for skills in SKILLS_BY_STAT.values()
        for skill in skills
    }
if "hp_max" not in st.session_state.pg:
    st.session_state.pg["hp_max"] = 1
if "hp_current" not in st.session_state.pg:
    st.session_state.pg["hp_current"] = int(st.session_state.pg.get("hp_max", 1))
if "hp_temp" not in st.session_state.pg:
    st.session_state.pg["hp_temp"] = 0
if "ac_base" not in st.session_state.pg:
    st.session_state.pg["ac_base"] = 10
if "ac_bonus" not in st.session_state.pg:
    st.session_state.pg["ac_bonus"] = 0
if "iniziativa_bonus" not in st.session_state.pg:
    st.session_state.pg["iniziativa_bonus"] = 0
if "speed_walk" not in st.session_state.pg:
    st.session_state.pg["speed_walk"] = 9
if "hit_die_type" not in st.session_state.pg:
    st.session_state.pg["hit_die_type"] = "d8"
if "hit_dice_total" not in st.session_state.pg:
    st.session_state.pg["hit_dice_total"] = 1
if "hit_dice_remaining" not in st.session_state.pg:
    st.session_state.pg["hit_dice_remaining"] = int(st.session_state.pg.get("hit_dice_total", 1))
if "level" not in st.session_state.pg:
    if "livello" in st.session_state.pg:
        st.session_state.pg["level"] = int(st.session_state.pg.get("livello", 1) or 1)
    else:
        st.session_state.pg["level"] = 1
else:
    st.session_state.pg["level"] = int(st.session_state.pg.get("level", 1) or 1)
if "hp_method" not in st.session_state.pg:
    st.session_state.pg["hp_method"] = "Medio"
if "hp_rolls" not in st.session_state.pg:
    st.session_state.pg["hp_rolls"] = ""
if "hp_first_level" not in st.session_state.pg:
    st.session_state.pg["hp_first_level"] = hit_die_max(
        st.session_state.pg.get("hit_die_type", "d8")
    )
missing_base_keys = any(f"stats_base_{k}" not in st.session_state for k in CARATTERISTICHE)
if st.session_state.get("_sync_ui_from_pg") or missing_base_keys or not all(
    k in st.session_state
    for k in (
        "ui_nome",
        "ui_classe_label",
        "ui_lineage",
        "ui_alignment",
        "ui_hp_max",
        "ui_hp_current",
        "ui_hp_temp",
        "ui_ac_base",
        "ui_ac_bonus",
        "ui_init_bonus",
        "ui_speed_walk",
        "ui_hit_die_type",
        "ui_hit_dice_remaining",
        "ui_level",
    )
):
    sync_widgets_from_pg(force=bool(st.session_state.get("_sync_ui_from_pg")))
    st.session_state["_sync_ui_from_pg"] = False

if "ui_level" in st.session_state:
    st.session_state.pg["level"] = int(
        st.session_state.get("ui_level", st.session_state.pg.get("level", 1))
    )


# Migrazione al volo (solo se serve)
if st.session_state.pg.get("classe") in LEGACY:
    st.session_state.pg["classe"] = LEGACY[st.session_state.pg["classe"]]

with st.sidebar:
    st.header("Personaggio")

    salvati = list_characters()
    scelta = st.selectbox("Personaggi salvati", ["(nessuno)"] + salvati, index=0)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("➕ Nuovo", use_container_width=True):
            st.session_state.pg = {
                "nome": "Nuovo PG",
                "classe": "warlock",
                "stats_base": {"for": 10, "des": 10, "cos": 10, "int": 10, "sag": 10, "car": 10},
                "asi_bonus": {"for": 0, "des": 0, "cos": 0, "int": 0, "sag": 0, "car": 0},
                "lineage": "none",
                "saving_throws_proficient": {k: False for k in CARATTERISTICHE},
                "skills": {
                    skill: {"proficient": False, "expertise": False}
                    for skills in SKILLS_BY_STAT.values()
                    for skill in skills
                },
                "hp_max": 1,
                "hp_current": 1,
                "hp_temp": 0,
                "ac_base": 10,
                "ac_bonus": 0,
                "iniziativa_bonus": 0,
                "speed_walk": 9,
                "hit_die_type": "d8",
                "hit_dice_total": 1,
                "hit_dice_remaining": 1,
                "level": 1,
                "hp_method": "Medio",
                "hp_rolls": "",
                "hp_first_level": hit_die_max("d8"),
                "alignment": "Neutrale",
            }
            st.session_state.current_slug = None
            st.session_state["_sync_ui_from_pg"] = True
            st.rerun()

    with c2:
        if st.button("💾 Salva", use_container_width=True):
            st.session_state.current_slug = save_character(st.session_state.pg)
            st.success(f"Salvato: {st.session_state.current_slug}")
            st.rerun()

    with c3:
        if st.button("📂 Carica", use_container_width=True) and scelta != "(nessuno)":
            loaded = load_character(scelta)
            if loaded:
                if loaded.get("classe") in LEGACY:
                    loaded["classe"] = LEGACY[loaded["classe"]]
                if "stats_base" not in loaded:
                    if "stats" in loaded:
                        loaded["stats_base"] = {
                            k: int(loaded["stats"].get(k, 10)) for k in CARATTERISTICHE
                        }
                    else:
                        loaded["stats_base"] = {k: 10 for k in CARATTERISTICHE}
                if "asi_bonus" not in loaded:
                    loaded["asi_bonus"] = {k: 0 for k in CARATTERISTICHE}
                if "lineage" not in loaded:
                    loaded["lineage"] = "none"
                if "saving_throws_proficient" not in loaded:
                    loaded["saving_throws_proficient"] = {k: False for k in CARATTERISTICHE}
                if "skills" not in loaded:
                    loaded["skills"] = {
                        skill: {"proficient": False, "expertise": False}
                        for skills in SKILLS_BY_STAT.values()
                        for skill in skills
                    }
                if "hp_max" not in loaded:
                    loaded["hp_max"] = 1
                if "hp_current" not in loaded:
                    loaded["hp_current"] = int(loaded.get("hp_max", 1))
                if "hp_temp" not in loaded:
                    loaded["hp_temp"] = 0
                if "ac_base" not in loaded:
                    loaded["ac_base"] = 10
                if "ac_bonus" not in loaded:
                    loaded["ac_bonus"] = 0
                if "iniziativa_bonus" not in loaded:
                    loaded["iniziativa_bonus"] = 0
                if "speed_walk" not in loaded:
                    loaded["speed_walk"] = 9
                if "hit_die_type" not in loaded:
                    loaded["hit_die_type"] = "d8"
                if "hit_dice_total" not in loaded:
                    loaded["hit_dice_total"] = 1
                if "hit_dice_remaining" not in loaded:
                    loaded["hit_dice_remaining"] = int(loaded.get("hit_dice_total", 1))
                if "level" not in loaded:
                    loaded["level"] = int(loaded.get("livello", 1) or 1)
                if "hp_method" not in loaded:
                    loaded["hp_method"] = "Medio"
                if "hp_rolls" not in loaded:
                    loaded["hp_rolls"] = ""
                if "hp_first_level" not in loaded:
                    loaded["hp_first_level"] = hit_die_max(loaded.get("hit_die_type", "d8"))
                if "alignment" not in loaded:
                    loaded["alignment"] = "Neutrale"
                st.session_state.pg = loaded
                st.session_state.current_slug = scelta
                st.session_state["_sync_ui_from_pg"] = True
            st.rerun()

    st.divider()

    class_slug = st.session_state.pg.get("classe")
    preset = CLASS_PRESETS_POINT_BUY.get(class_slug)
    if preset:
        preset_choice = st.selectbox(
            "Preset consigliato",
            ["(nessuno)", "Preset consigliato (Point Buy 27)"],
            index=0,
            label_visibility="collapsed",
        )
        apply_preset = st.button("✅ Applica preset", use_container_width=True)
        if apply_preset and preset_choice != "(nessuno)":
            st.session_state.pg["stats_base"] = preset.copy()
            st.session_state.pg["stat_method"] = "preset_point_buy"
            st.success("Preset applicato.")
            st.session_state["_sync_ui_from_pg"] = True
            st.rerun()

    bc = bonus_competenza(int(st.session_state.pg["level"]))
    st.info(f"Bonus Competenza: {fmt_bonus(bc)}")

    st.divider()

    # Export / Import
    with st.expander("Import/Export", expanded=False):
        st.download_button(
            "⬇️ Esporta JSON",
            data=json.dumps(st.session_state.pg, ensure_ascii=False, indent=2),
            file_name=f"{st.session_state.pg.get('nome','personaggio')}.json",
            mime="application/json",
            use_container_width=True,
        )

        up = st.file_uploader("⬆️ Importa JSON", type=["json"])
        if up is not None:
            try:
                imported = json.loads(up.read().decode("utf-8"))
                if not isinstance(imported, dict):
                    raise ValueError("Il JSON deve essere un oggetto.")
                if imported.get("classe") in LEGACY:
                    imported["classe"] = LEGACY[imported["classe"]]
                if "stats_base" not in imported:
                    if "stats" in imported:
                        imported["stats_base"] = {
                            k: int(imported["stats"].get(k, 10)) for k in CARATTERISTICHE
                        }
                    else:
                        imported["stats_base"] = {k: 10 for k in CARATTERISTICHE}
                if "asi_bonus" not in imported:
                    imported["asi_bonus"] = {k: 0 for k in CARATTERISTICHE}
                if "lineage" not in imported:
                    imported["lineage"] = "none"
                if "saving_throws_proficient" not in imported:
                    imported["saving_throws_proficient"] = {k: False for k in CARATTERISTICHE}
                if "skills" not in imported:
                    imported["skills"] = {
                        skill: {"proficient": False, "expertise": False}
                        for skills in SKILLS_BY_STAT.values()
                        for skill in skills
                    }
                if "hp_max" not in imported:
                    imported["hp_max"] = 1
                if "hp_current" not in imported:
                    imported["hp_current"] = int(imported.get("hp_max", 1))
                if "hp_temp" not in imported:
                    imported["hp_temp"] = 0
                if "ac_base" not in imported:
                    imported["ac_base"] = 10
                if "ac_bonus" not in imported:
                    imported["ac_bonus"] = 0
                if "iniziativa_bonus" not in imported:
                    imported["iniziativa_bonus"] = 0
                if "speed_walk" not in imported:
                    imported["speed_walk"] = 9
                if "hit_die_type" not in imported:
                    imported["hit_die_type"] = "d8"
                if "hit_dice_total" not in imported:
                    imported["hit_dice_total"] = 1
                if "hit_dice_remaining" not in imported:
                    imported["hit_dice_remaining"] = int(imported.get("hit_dice_total", 1))
                if "level" not in imported:
                    imported["level"] = int(imported.get("livello", 1) or 1)
                if "hp_method" not in imported:
                    imported["hp_method"] = "Medio"
                if "hp_rolls" not in imported:
                    imported["hp_rolls"] = ""
                if "hp_first_level" not in imported:
                    imported["hp_first_level"] = hit_die_max(
                        imported.get("hit_die_type", "d8")
                    )
                if "alignment" not in imported:
                    imported["alignment"] = "Neutrale"
                st.session_state.pg = imported
                st.session_state.current_slug = None
                st.success("Import completato.")
                st.session_state["_sync_ui_from_pg"] = True
                st.rerun()
            except Exception as exc:
                st.error(f"Errore durante l'import: {exc}")

lineage_labels = [
    "Nessuno",
    "Umano (+1 a tutto)",
    "Umano Variante (+1 +1)",
    "Personalizzato (+2/+1)",
]

st.markdown('<div class="topbar"><div class="topbar-inner">', unsafe_allow_html=True)
top_cols = st.columns([2, 2, 2, 1, 2])
with top_cols[0]:
    st.text_input("Nome", key="ui_nome", placeholder="Nome PG", label_visibility="collapsed")
with top_cols[1]:
    st.selectbox(
        "Razza/Lineage",
        lineage_labels,
        key="ui_lineage",
        label_visibility="collapsed",
    )
with top_cols[2]:
    st.selectbox("Classe", LABELS, key="ui_classe_label", label_visibility="collapsed")
with top_cols[3]:
    st.number_input(
        "Lv",
        min_value=1,
        max_value=20,
        step=1,
        key="ui_level",
        label_visibility="collapsed",
    )
with top_cols[4]:
    st.selectbox(
        "Allineamento",
        ALIGNMENTS,
        key="ui_alignment",
        label_visibility="collapsed",
    )
st.markdown("</div></div>", unsafe_allow_html=True)

st.session_state.pg["nome"] = st.session_state.get("ui_nome", "")
selected_label = st.session_state.get("ui_classe_label", LABELS[0])
prev_slug = st.session_state.pg.get("classe")
st.session_state.pg["classe"] = LABEL_TO_SLUG[selected_label]
if (
    st.session_state.pg["classe"] != prev_slug
    and st.session_state.pg.get("saving_throws_auto", True)
):
    profs = set(SAVING_THROW_PROF_BY_CLASS.get(st.session_state.pg["classe"], []))
    st.session_state.pg["saving_throws_proficient"] = {k: (k in profs) for k in CARATTERISTICHE}
    st.session_state["_sync_ui_from_pg"] = True
    st.rerun()

lineage_slug = {
    "Nessuno": "none",
    "Umano (+1 a tutto)": "human",
    "Umano Variante (+1 +1)": "vhuman",
    "Personalizzato (+2/+1)": "custom_2_1",
}[st.session_state.get("ui_lineage", "Nessuno")]
st.session_state.pg["lineage"] = lineage_slug
st.session_state.pg["alignment"] = st.session_state.get("ui_alignment", "Neutrale")
st.session_state.pg["level"] = int(st.session_state.get("ui_level", st.session_state.pg.get("level", 1)))

bc = bonus_competenza(int(st.session_state.pg["level"]))
st.caption(f"Bonus Competenza: {fmt_bonus(bc)}")

st.title("🎲 DnD Sheet")
st.caption("Local-first: i personaggi si salvano in file JSON nella cartella db/characters/.")

st.header("Scheda")

if st.session_state.pg.get("lineage") == "none":
    st.session_state.pg["asi_bonus"] = {k: 0 for k in CARATTERISTICHE}
elif st.session_state.pg.get("lineage") == "human":
    st.session_state.pg["asi_bonus"] = {k: 1 for k in CARATTERISTICHE}
elif st.session_state.pg.get("lineage") == "vhuman":
    labels = [STATS_LABELS[k] for k in CARATTERISTICHE]
    st.selectbox("Bonus +1 (1)", labels, key="ui_vhuman_a")
    vhuman_a = st.session_state["ui_vhuman_a"]
    vhuman_b_options = [l for l in labels if l != vhuman_a]
    st.selectbox("Bonus +1 (2)", vhuman_b_options, key="ui_vhuman_b")
    vhuman_b = st.session_state["ui_vhuman_b"]
    asi = {k: 0 for k in CARATTERISTICHE}
    asi[STAT_LABEL_TO_KEY[vhuman_a]] = 1
    asi[STAT_LABEL_TO_KEY[vhuman_b]] = 1
    st.session_state.pg["asi_bonus"] = asi
elif st.session_state.pg.get("lineage") == "custom_2_1":
    labels = [STATS_LABELS[k] for k in CARATTERISTICHE]
    st.selectbox("Bonus +2", labels, key="ui_custom_plus2")
    plus2 = st.session_state["ui_custom_plus2"]
    plus1_options = [l for l in labels if l != plus2]
    st.selectbox("Bonus +1", plus1_options, key="ui_custom_plus1")
    plus1 = st.session_state["ui_custom_plus1"]
    asi = {k: 0 for k in CARATTERISTICHE}
    asi[STAT_LABEL_TO_KEY[plus2]] = 2
    asi[STAT_LABEL_TO_KEY[plus1]] = 1
    st.session_state.pg["asi_bonus"] = asi
st.subheader("Caratteristiche")
cols = st.columns(6)
for col, key in zip(cols, ["for", "des", "cos", "int", "sag", "car"], strict=True):
    with col:
        label = STATS_LABELS.get(key, key.upper())
        base_key = f"stats_base_{key}"
        base_value = int(st.session_state[base_key])
        bonus = int(st.session_state.pg["asi_bonus"].get(key, 0))
        total = base_value + bonus
        mod = mod_caratteristica(total)
        st.markdown(f"**{label}**")
        st.markdown(
            f"""
            <div style="border:1px solid #ddd;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:28px;font-weight:700;line-height:1;">{total}</div>
              <div style="margin-top:6px;font-weight:600;">Mod {fmt_bonus(mod)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.number_input(
            "",
            min_value=3,
            max_value=18,
            step=1,
            key=base_key,
            label_visibility="collapsed",
        )
        st.session_state.pg["stats_base"][key] = int(st.session_state[base_key])

totals = total_stats(st.session_state.pg["stats_base"], st.session_state.pg["asi_bonus"])
st.session_state.pg["stats"] = totals
st.caption("Base + Bonus = Totale")

bc = bonus_competenza(int(st.session_state.pg["level"]))
tabs = st.tabs(["Tiri Salvezza", "Abilità", "Combattimento"])

with tabs[0]:
    st.subheader("Tiri Salvezza")
    auto_enabled = st.session_state.pg.get("saving_throws_auto", True)
    auto_label = "ON" if auto_enabled else "OFF"
    st.caption(f"Auto: {auto_label}")

    row1 = st.columns(3)
    row2 = st.columns(3)
    for col, key in zip(row1, ["for", "des", "cos"], strict=True):
        with col:
            st.subheader(STATS_LABELS.get(key, key.upper()))
            st.checkbox(
                "Competente",
                key=f"st_prof_{key}",
                on_change=_on_saving_throw_change,
                args=(key,),
                disabled=auto_enabled,
            )
            st.session_state.pg["saving_throws_proficient"][key] = bool(
                st.session_state[f"st_prof_{key}"]
            )
            base = mod_caratteristica(int(st.session_state.pg["stats"].get(key, 10)))
            total = base + (bc if st.session_state[f"st_prof_{key}"] else 0)
            st.caption(fmt_bonus(total))
    for col, key in zip(row2, ["int", "sag", "car"], strict=True):
        with col:
            st.subheader(STATS_LABELS.get(key, key.upper()))
            st.checkbox(
                "Competente",
                key=f"st_prof_{key}",
                on_change=_on_saving_throw_change,
                args=(key,),
                disabled=auto_enabled,
            )
            st.session_state.pg["saving_throws_proficient"][key] = bool(
                st.session_state[f"st_prof_{key}"]
            )
            base = mod_caratteristica(int(st.session_state.pg["stats"].get(key, 10)))
            total = base + (bc if st.session_state[f"st_prof_{key}"] else 0)
            st.caption(fmt_bonus(total))

    if st.button("Reimposta TS da classe", use_container_width=False):
        st.session_state.pg["saving_throws_auto"] = True
        profs = set(SAVING_THROW_PROF_BY_CLASS.get(st.session_state.pg.get("classe"), []))
        st.session_state.pg["saving_throws_proficient"] = {k: (k in profs) for k in CARATTERISTICHE}
        st.session_state["_sync_ui_from_pg"] = True
        st.rerun()

with tabs[1]:
    st.subheader("Abilità")
    filter_options = ["Tutte", "FOR", "DES", "INT", "SAG", "CAR"]
    col_filter, col_search = st.columns([1, 2])
    with col_filter:
        st.selectbox("Filtro caratteristica", filter_options, key="ui_skill_filter")
    with col_search:
        st.text_input("Ricerca", placeholder="Cerca abilità...", key="ui_skill_search")

    selected_filter = st.session_state.get("ui_skill_filter", "Tutte")
    query = st.session_state.get("ui_skill_search", "").strip().lower()

    ordered_stats = ["for", "des", "int", "sag", "car"]
    skill_rows = [
        (stat_key, skill)
        for stat_key in ordered_stats
        for skill in SKILLS_BY_STAT.get(stat_key, [])
    ]
    for stat_key, skill in skill_rows:
        stat_label = STATS_LABELS.get(stat_key, stat_key.upper())
        if selected_filter != "Tutte" and selected_filter != stat_label:
            continue
        if query and query not in skill.lower():
            continue
        col_name, col_prof, col_exp, col_val = st.columns([4, 1, 1, 1])
        with col_name:
            st.write(f"{skill} ({stat_label})")
        with col_prof:
            st.checkbox(
                "Comp.",
                key=f"sk_prof_{skill}",
                on_change=_on_skill_prof_change,
                args=(skill,),
            )
        with col_exp:
            st.checkbox(
                "Exp.",
                key=f"sk_exp_{skill}",
                disabled=not st.session_state[f"sk_prof_{skill}"],
            )
        prof = bool(st.session_state[f"sk_prof_{skill}"])
        exp = bool(st.session_state[f"sk_exp_{skill}"])
        st.session_state.pg["skills"][skill] = {"proficient": prof, "expertise": exp and prof}
        with col_val:
            mod = mod_caratteristica(int(st.session_state.pg["stats"].get(stat_key, 10)))
            total = mod + (2 * bc if exp else (bc if prof else 0))
            st.write(fmt_bonus(total))

with tabs[2]:
    st.subheader("Combattimento")
    ac_total = int(st.session_state.pg.get("ac_base", 10)) + int(
        st.session_state.pg.get("ac_bonus", 0)
    )
    des_mod = mod_caratteristica(int(st.session_state.pg["stats"].get("des", 10)))
    init_total = des_mod + int(st.session_state.pg.get("iniziativa_bonus", 0))
    sag_mod = mod_caratteristica(int(st.session_state.pg["stats"].get("sag", 10)))
    percezione = st.session_state.pg.get("skills", {}).get("Percezione")
    if percezione:
        prof = bool(percezione.get("proficient", False))
        exp = bool(percezione.get("expertise", False)) and prof
        percezione_bonus = sag_mod + (2 * bc if exp else (bc if prof else 0))
    else:
        percezione_bonus = sag_mod
    passive_perception = 10 + percezione_bonus
    metric_cols = st.columns(3)
    with metric_cols[0]:
        st.metric("AC totale", ac_total)
    with metric_cols[1]:
        st.metric("Iniziativa", fmt_bonus(init_total))
    with metric_cols[2]:
        st.metric("Percezione passiva", passive_perception)

    row_quick = st.columns(2)
    with row_quick[0]:
        st.number_input("Velocità (m)", min_value=0, key="ui_speed_walk")
    with row_quick[1]:
        st.number_input("Bonus Iniziativa", min_value=-20, max_value=20, key="ui_init_bonus")

    st.subheader("Punti Ferita")
    pf_col1, pf_col2, pf_col3 = st.columns(3)
    with pf_col1:
        st.caption(f"Livello: {int(st.session_state.pg.get('level', 1))}")
    with pf_col2:
        st.selectbox("Metodo", ["Medio", "Tiro"], key="ui_hp_method")
        if st.session_state.get("ui_hp_method", "Medio") == "Tiro":
            st.text_input("Tiri HP (livelli 2+)", key="ui_hp_rolls", placeholder="es: 6,5,7")
    with pf_col3:
        st.number_input("HP 1° livello", min_value=1, key="ui_hp_first_level")

    if st.session_state.get("ui_hp_method", "Medio") == "Tiro":
        level_warn = int(st.session_state.pg.get("level", 1))
        needed = max(0, level_warn - 1)
        rolls_valid = []
        for token in str(st.session_state.get("ui_hp_rolls", "")).split(","):
            token = token.strip()
            if not token:
                continue
            try:
                rolls_valid.append(int(token))
            except ValueError:
                continue
        given = len(rolls_valid)
        if given < needed:
            st.warning(
                f"Servono {needed} tiri (dal 2° al {level_warn}°). "
                f"Inseriti: {given}. Mancano: {needed - given}."
            )

    btn_col, cap_col = st.columns([1, 2])
    with btn_col:
        calc_hp = st.button("Calcola HP Max")
    with cap_col:
        level_preview = int(st.session_state.pg.get("level", 1))
        hit_die_preview = str(st.session_state.get("ui_hit_die_type", "d8"))
        hp_method_preview = str(st.session_state.get("ui_hp_method", "Medio"))
        inc_preview = (
            f"{max(level_preview - 1, 0)}×max(1, {hit_die_avg(hit_die_preview)}+modCOS)"
            if hp_method_preview == "Medio"
            else "somma max(1, tiro+modCOS)"
        )
        cos_preview = int(st.session_state.pg.get("stats", {}).get("cos", 10))
        mod_cos_preview = mod_caratteristica(cos_preview)
        cap_col.caption(
            f"HP = max(1, base + modCOS) + {inc_preview} (modCOS={fmt_bonus(mod_cos_preview)})"
        )

    if calc_hp:
        level = int(st.session_state.pg.get("level", 1))
        hp_method = str(st.session_state.get("ui_hp_method", "Medio"))
        hp_rolls = str(st.session_state.get("ui_hp_rolls", ""))
        hp_first_level = int(
            st.session_state.get(
                "ui_hp_first_level",
                hit_die_max(st.session_state.pg.get("hit_die_type", "d8")),
            )
        )
        hit_die_type = str(st.session_state.get("ui_hit_die_type", "d8"))
        cos_total = int(st.session_state.pg.get("stats", {}).get("cos", 10))
        mod_cos = mod_caratteristica(cos_total)

        gain1 = max(1, hp_first_level + mod_cos)
        inc = 0
        if level > 1:
            if hp_method == "Medio":
                per_level_gain = max(1, hit_die_avg(hit_die_type) + mod_cos)
                inc = (level - 1) * per_level_gain
            else:
                rolls = []
                for token in hp_rolls.split(","):
                    token = token.strip()
                    if not token:
                        continue
                    try:
                        rolls.append(int(token))
                    except ValueError:
                        continue
                for idx in range(level - 1):
                    r = rolls[idx] if idx < len(rolls) else 0
                    inc += max(1, r + mod_cos)
        hp_max_calc = max(1, gain1 + inc)

        old_hp_max = int(st.session_state.pg.get("hp_max", 1))
        old_current = int(st.session_state.pg.get("hp_current", old_hp_max))
        was_full = old_current == old_hp_max

        st.session_state.pg["hp_max"] = hp_max_calc
        st.session_state["ui_hp_max"] = hp_max_calc

        if was_full:
            new_current = hp_max_calc
        else:
            new_current = min(old_current, hp_max_calc)
        new_current = max(0, new_current)
        st.session_state.pg["hp_current"] = new_current
        if "ui_hp_current" in st.session_state:
            st.session_state["ui_hp_current"] = new_current

    col_hp, col_hp2, col_hp3 = st.columns(3)
    with col_hp:
        st.number_input("HP Max", min_value=1, key="ui_hp_max")
    with col_hp2:
        st.number_input("HP Attuali", min_value=0, key="ui_hp_current")
    with col_hp3:
        st.number_input("HP Temp", min_value=0, key="ui_hp_temp")

    col_ac, col_ac2 = st.columns(2)
    with col_ac:
        st.number_input("CA Base", min_value=0, key="ui_ac_base")
    with col_ac2:
        st.number_input("Bonus CA", min_value=-20, max_value=20, key="ui_ac_bonus")

    hit_dice_total = int(st.session_state.pg.get("level", 1))
    old_total = int(st.session_state.pg.get("hit_dice_total", hit_dice_total))
    old_remaining = int(
        st.session_state.get(
            "ui_hit_dice_remaining",
            st.session_state.pg.get("hit_dice_remaining", old_total),
        )
    )
    if old_remaining == old_total:
        hit_dice_remaining = hit_dice_total
    else:
        hit_dice_remaining = max(0, min(old_remaining, hit_dice_total))
    st.session_state.pg["hit_dice_total"] = hit_dice_total
    st.session_state.pg["hit_dice_remaining"] = hit_dice_remaining
    st.session_state["ui_hit_dice_remaining"] = hit_dice_remaining

    st.subheader("Dadi Vita")
    col_hd1, col_hd2, col_hd3 = st.columns(3)
    with col_hd1:
        st.selectbox("Tipo Dado Vita", ["d6", "d8", "d10", "d12"], key="ui_hit_die_type")
    with col_hd2:
        st.metric("Dadi Vita Totali", hit_dice_total)
    with col_hd3:
        st.number_input(
            "Dadi Vita Rimasti",
            min_value=0,
            max_value=hit_dice_total,
            key="ui_hit_dice_remaining",
        )

    st.session_state.pg["hp_max"] = int(st.session_state.get("ui_hp_max", 1))
    st.session_state.pg["hp_current"] = int(
        st.session_state.get("ui_hp_current", st.session_state.pg["hp_max"])
    )
    st.session_state.pg["hp_temp"] = int(st.session_state.get("ui_hp_temp", 0))
    st.session_state.pg["ac_base"] = int(st.session_state.get("ui_ac_base", 10))
    st.session_state.pg["ac_bonus"] = int(st.session_state.get("ui_ac_bonus", 0))
    st.session_state.pg["iniziativa_bonus"] = int(st.session_state.get("ui_init_bonus", 0))
    st.session_state.pg["speed_walk"] = int(st.session_state.get("ui_speed_walk", 9))
    st.session_state.pg["hit_die_type"] = str(st.session_state.get("ui_hit_die_type", "d8"))
    remaining = int(st.session_state.get("ui_hit_dice_remaining", hit_dice_total))
    remaining = max(0, min(remaining, hit_dice_total))
    st.session_state.pg["hit_dice_remaining"] = remaining
    st.session_state.pg["hp_method"] = str(st.session_state.get("ui_hp_method", "Medio"))
    st.session_state.pg["hp_rolls"] = str(st.session_state.get("ui_hp_rolls", ""))
    st.session_state.pg["hp_first_level"] = int(
        st.session_state.get(
            "ui_hp_first_level",
            hit_die_max(st.session_state.pg.get("hit_die_type", "d8")),
        )
    )

st.subheader("Incantatore")
spell_ability = SPELLCASTING_ABILITY_BY_CLASS.get(st.session_state.pg.get("classe"))
if not spell_ability:
    st.write("Questa classe non lancia incantesimi.")
else:
    level = int(st.session_state.pg.get("level", 1))
    bc = bonus_competenza(level)
    mod = mod_caratteristica(int(st.session_state.pg["stats"].get(spell_ability, 10)))
    spell_attack = bc + mod
    spell_dc = 8 + bc + mod
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        label = STATS_LABELS.get(spell_ability, spell_ability.upper())
        st.write(f"Caratteristica: {label}")
        st.caption(f"Mod: {fmt_bonus(mod)}")
    with col_b:
        st.write("Attacco Incantesimi")
        st.subheader(fmt_bonus(spell_attack))
    with col_c:
        st.write("CD Incantesimi")
        st.subheader(str(spell_dc))

with st.expander("Debug (JSON)", expanded=False):
    st.json(st.session_state.pg)

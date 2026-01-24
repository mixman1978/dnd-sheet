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


st.set_page_config(page_title="DnD Sheet", page_icon="🎲", layout="wide")

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

# Migrazione eventuale (se in vecchi JSON avevi "Warlock" ecc.)
LEGACY = {
    "Warlock": "warlock",
    "Wizard": "wizard",
    "Cleric": "cleric",
    "Fighter": "fighter",
}


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
    if force or "ui_nome" not in st.session_state:
        st.session_state["ui_nome"] = str(pg.get("nome", ""))
    if force or "ui_livello" not in st.session_state:
        st.session_state["ui_livello"] = int(pg.get("livello", 1) or 1)
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


def _on_skill_prof_change(skill: str) -> None:
    if not st.session_state.get(f"sk_prof_{skill}", False):
        st.session_state[f"sk_exp_{skill}"] = False


def _on_saving_throw_change(stat_key: str) -> None:
    pg = st.session_state.pg
    pg["saving_throws_auto"] = False
    pg.setdefault("saving_throws_proficient", {})
    pg["saving_throws_proficient"][stat_key] = bool(st.session_state.get(f"st_prof_{stat_key}", False))

st.title("🎲 DnD Sheet")
st.caption("Local-first: i personaggi si salvano in file JSON nella cartella db/characters/.")

# Stato iniziale
if "pg" not in st.session_state:
    st.session_state.pg = {
        "nome": "Azir",
        "classe": "warlock",
        "livello": 1,
        "stats_base": {"for": 10, "des": 10, "cos": 10, "int": 10, "sag": 10, "car": 10},
        "asi_bonus": {"for": 0, "des": 0, "cos": 0, "int": 0, "sag": 0, "car": 0},
        "lineage": "none",
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
missing_base_keys = any(f"stats_base_{k}" not in st.session_state for k in CARATTERISTICHE)
if st.session_state.get("_sync_ui_from_pg") or missing_base_keys or not all(
    k in st.session_state for k in ("ui_nome", "ui_livello", "ui_classe_label", "ui_lineage")
):
    sync_widgets_from_pg(force=bool(st.session_state.get("_sync_ui_from_pg")))
    st.session_state["_sync_ui_from_pg"] = False


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
                "livello": 1,
                "stats_base": {"for": 10, "des": 10, "cos": 10, "int": 10, "sag": 10, "car": 10},
                "asi_bonus": {"for": 0, "des": 0, "cos": 0, "int": 0, "sag": 0, "car": 0},
                "lineage": "none",
                "saving_throws_proficient": {k: False for k in CARATTERISTICHE},
                "skills": {
                    skill: {"proficient": False, "expertise": False}
                    for skills in SKILLS_BY_STAT.values()
                    for skill in skills
                },
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
                st.session_state.pg = loaded
                st.session_state.current_slug = scelta
                st.session_state["_sync_ui_from_pg"] = True
            st.rerun()

    st.divider()

    # Editor campi base
    st.text_input("Nome", key="ui_nome")
    st.session_state.pg["nome"] = st.session_state.get("ui_nome", "")

    st.selectbox("Classe", LABELS, key="ui_classe_label")
    selected_label = st.session_state["ui_classe_label"]
    prev_slug = st.session_state.pg.get("classe")
    st.session_state.pg["classe"] = LABEL_TO_SLUG[selected_label]
    if (
        st.session_state.pg["classe"] != prev_slug
        and st.session_state.pg.get("saving_throws_auto", True)
    ):
        profs = set(SAVING_THROW_PROF_BY_CLASS.get(st.session_state.pg["classe"], []))
        st.session_state.pg["saving_throws_proficient"] = {
            k: (k in profs) for k in CARATTERISTICHE
        }
        st.session_state["_sync_ui_from_pg"] = True
        st.rerun()

    st.subheader("Razza/Lineage")
    lineage_labels = [
        "Nessuno",
        "Umano (+1 a tutto)",
        "Umano Variante (+1 +1)",
        "Personalizzato (+2/+1)",
    ]
    st.selectbox("Lineage", lineage_labels, key="ui_lineage")
    lineage_slug = {
        "Nessuno": "none",
        "Umano (+1 a tutto)": "human",
        "Umano Variante (+1 +1)": "vhuman",
        "Personalizzato (+2/+1)": "custom_2_1",
    }[st.session_state["ui_lineage"]]
    st.session_state.pg["lineage"] = lineage_slug

    if lineage_slug == "none":
        st.session_state.pg["asi_bonus"] = {k: 0 for k in CARATTERISTICHE}
    elif lineage_slug == "human":
        st.session_state.pg["asi_bonus"] = {k: 1 for k in CARATTERISTICHE}
    elif lineage_slug == "vhuman":
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
    elif lineage_slug == "custom_2_1":
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

    class_slug = st.session_state.pg.get("classe")
    preset = CLASS_PRESETS_POINT_BUY.get(class_slug)
    if preset:
        preset_choice = st.selectbox(
            "Preset consigliato",
            ["(nessuno)", "Preset consigliato (Point Buy 27)"],
            index=0,
        )
        if st.button("Applica preset", use_container_width=True) and preset_choice != "(nessuno)":
            st.session_state.pg["stats_base"] = preset.copy()
            st.session_state.pg["stat_method"] = "preset_point_buy"
            st.success("Preset applicato.")
            st.session_state["_sync_ui_from_pg"] = True
            st.rerun()

    st.number_input("Livello", min_value=1, max_value=20, key="ui_livello")
    st.session_state.pg["livello"] = int(st.session_state.get("ui_livello", 1))

    bc = bonus_competenza(int(st.session_state.pg["livello"]))
    st.info(f"Bonus Competenza: {fmt_bonus(bc)}")

    st.divider()

    # Export / Import
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
            st.session_state.pg = imported
            st.session_state.current_slug = None
            st.success("Import completato.")
            st.session_state["_sync_ui_from_pg"] = True
            st.rerun()
        except Exception as exc:
            st.error(f"Errore durante l'import: {exc}")

st.header("Scheda")
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
        bonus_text = fmt_bonus(bonus)
        bonus_line = (
            f"Base {base_value} \u2022 Bonus {bonus_text}" if bonus != 0 else f"Base {base_value}"
        )
        st.markdown(f"**{label}**")
        st.markdown(
            f"""
            <div style="border:1px solid #ddd;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:28px;font-weight:700;line-height:1;">{total}</div>
              <div style="margin-top:6px;font-weight:600;">Mod {fmt_bonus(mod)}</div>
              <div style="margin-top:4px;font-size:12px;color:#666;">{bonus_line}</div>
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
st.caption("Base + Bonus = Totale (usato per i calcoli)")

bc = bonus_competenza(int(st.session_state.pg["livello"]))
tabs = st.tabs(["Tiri Salvezza", "Abilità"])

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

st.subheader("Incantatore")
spell_ability = SPELLCASTING_ABILITY_BY_CLASS.get(st.session_state.pg.get("classe"))
if not spell_ability:
    st.write("Questa classe non lancia incantesimi.")
else:
    level = int(st.session_state.pg.get("livello", 1))
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

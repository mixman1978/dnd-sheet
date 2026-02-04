from __future__ import annotations

import json
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
    mod,
    prof_bonus,
    total_stats,
    hp_max,
    hit_die,
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
    pg["level"] = clamp_int(pg.get("level"), 1, 1, 20)

    if not isinstance(pg.get("stats_base"), dict):
        pg["stats_base"] = dict(DEFAULT_PG["stats_base"])
    for s in STATS:
        pg["stats_base"][s] = clamp_int(pg["stats_base"].get(s), 10, 3, 20)

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
    return pg


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


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "dev-secret-key-change-me"

    # Garantisce che lo schema esista all'avvio.
    with connect() as conn:
        ensure_schema(conn)

    @app.route("/", methods=["GET", "POST"])
    def index():
        pg = get_pg()

        if request.method == "POST":
            pg["nome"] = (request.form.get("nome") or pg.get("nome") or "personaggio").strip()
            pg["lineage"] = normalize_choice(request.form.get("lineage"), LINEAGES, pg["lineage"])
            pg["classe"] = normalize_choice(request.form.get("classe"), CLASSES, pg["classe"])
            pg["alignment"] = normalize_choice(request.form.get("alignment"), ALIGNMENTS, pg["alignment"])
            pg["level"] = clamp_int(request.form.get("level"), pg["level"], 1, 20)

            for s in STATS:
                pg["stats_base"][s] = clamp_int(request.form.get(f"stat_{s}"), pg["stats_base"][s], 3, 20)

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

            save_pg(pg)
            return redirect(url_for("index"))

        bonus = get_lineage_bonus(pg)
        totals = total_stats(pg["stats_base"], bonus)
        pb = prof_bonus(pg["level"])
        initiative = mod(totals["des"])
        dex_mod = mod(totals["des"])
        armor_type = pg.get("armor_type", "none")
        if armor_type == "medium":
            dex_to_ac = min(dex_mod, 2)
        elif armor_type == "heavy":
            dex_to_ac = 0
        else:
            dex_to_ac = dex_mod
        ac = 10 + dex_to_ac + (2 if pg.get("has_shield") else 0) + int(pg.get("ac_bonus", 0))
        speed_auto = 9
        st_prof = set(saving_throws(pg["classe"]))
        saving_rows = []
        for s in STATS:
            b = mod(totals[s]) + (pb if s in st_prof else 0)
            saving_rows.append(
                {
                    "stat": s,
                    "label": STAT_LABEL[s],
                    "bonus": b,
                    "proficient": s in st_prof,
                }
            )
        con_mod = mod(totals["cos"])
        hpmax = int(hp_max(pg["level"], pg["classe"], con_mod, "medio"))

        allowed_armor = ALLOWED_ARMOR_BY_CLASS.get(pg["classe"], ["none", "light", "medium", "heavy"])
        shield_allowed = ALLOWED_SHIELD_BY_CLASS.get(pg["classe"], True)

        # Spellcasting summary (only for classes that cast spells)
        spell_ability = spellcasting_ability(pg["classe"])
        spell_ability_label = STAT_LABEL.get(spell_ability) if spell_ability else None
        spell_mod = mod(totals[spell_ability]) if spell_ability else None
        spell_dc = (8 + pb + spell_mod) if spell_mod is not None else None
        spell_attack = (pb + spell_mod) if spell_mod is not None else None

        mezzelfo_opts = [(s, STAT_LABEL[s]) for s in STATS if s != "car"]

        sc = class_skill_choices(pg["classe"]) or {}
        choose_n = int(sc.get("choose") or 0)
        allowed_skills = sc.get("from") or sorted(SKILLS.keys())
        skills_filtered = [sk for sk in pg["skills_proficient"] if sk in allowed_skills]
        if choose_n > 0 and len(skills_filtered) > choose_n:
            skills_filtered = skills_filtered[:choose_n]
        if skills_filtered != pg["skills_proficient"]:
            pg["skills_proficient"] = skills_filtered
            save_pg(pg)

        prof_set = set(pg["skills_proficient"])
        all_skills = sorted(SKILLS.keys())
        skill_rows = []
        for sk in all_skills:
            stat = SKILLS[sk]
            proficient = sk in prof_set
            bonus_val = mod(totals[stat]) + (pb if proficient else 0)
            skill_rows.append(
                {
                    "name": sk,
                    "stat": stat,
                    "stat_label": STAT_LABEL[stat],
                    "bonus": bonus_val,
                    "proficient": proficient,
                    "selectable": sk in allowed_skills,
                }
            )

        # Passive Perception: 10 + WIS mod + PB if proficient in Percezione
        wis_mod = mod(totals["sag"])
        passive_perception = 10 + wis_mod + (pb if "Percezione" in prof_set else 0)

        # Base attacks (no weapon/inventory yet)
        melee_attack_bonus = mod(totals["for"]) + (pb if pg.get("atk_prof_melee") else 0)
        ranged_attack_bonus = mod(totals["des"]) + (pb if pg.get("atk_prof_ranged") else 0)

        characters = list_characters()

        return render_template(
            "index.html",
            pg=pg,
            bonus=bonus,
            totals=totals,
            pb=pb,
            hpmax=hpmax,
            hit_die=hit_die(pg["classe"]),
            mezzelfo_opts=mezzelfo_opts,
            choose_n=choose_n,
            allowed_skills=allowed_skills,
            skill_rows=skill_rows,
            saving_rows=saving_rows,
            initiative=initiative,
            ac=ac,
            dex_mod=dex_mod,
            characters=characters,
            passive_perception=passive_perception,
            melee_attack_bonus=melee_attack_bonus,
            ranged_attack_bonus=ranged_attack_bonus,
            speed_auto=speed_auto,
            allowed_armor=allowed_armor,
            shield_allowed=shield_allowed,
            spell_ability=spell_ability,
            spell_ability_label=spell_ability_label,
            spell_mod=spell_mod,
            spell_dc=spell_dc,
            spell_attack=spell_attack,
            STATS=STATS,
            STAT_LABEL=STAT_LABEL,
            CLASSES=CLASSES,
            LINEAGES=LINEAGES,
            ALIGNMENTS=ALIGNMENTS,
        )

    @app.post("/save_character")
    def save_character():
        pg = get_pg()
        name = (pg.get("nome") or "personaggio").strip() or "personaggio"
        try:
            char_id = save_character_to_db(name, pg)
            flash(f"Salvato: {name} (#{char_id})", "success")
        except Exception:
            flash("Errore durante il salvataggio.", "danger")
        return redirect(url_for("index"))

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
                limit=page_size + 1,
                offset=(page - 1) * page_size,
            )
            has_next = len(raw_results) > page_size
            results = raw_results[:page_size]
        else:
            results = []
        owned = list_character_spells(character_id) if character_id else []
        characters = list_characters()

        return render_template(
            "spells.html",
            pg=pg,
            q=q,
            level=level,
            class_code=class_code,
            class_options=class_options,
            ritual_only=ritual_only,
            concentration_only=concentration_only,
            pg_limits=pg_limits,
            pg_filter_class_label=pg_filter_class_label,
            pg_filter_max_spell_level=pg_filter_max_spell_level,
            page=page,
            has_prev=has_prev,
            has_next=has_next,
            results=results,
            owned=owned,
            characters=characters,
        )

    @app.post("/spells/add")
    def spells_add():
        character_id = _ensure_current_character_id()
        spell_id = clamp_int(request.form.get("spell_id"), 0, 0, None)
        if character_id and spell_id:
            add_spell_to_character(character_id, spell_id)
        return redirect(
            url_for(
                "spells",
                q=request.form.get("q") or "",
                level=request.form.get("level") or "",
                class_code=request.form.get("class_code") or "",
                ritual_only=request.form.get("ritual_only") or "",
                concentration_only=request.form.get("concentration_only") or "",
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
                pg_limits=request.form.get("pg_limits") or request.form.get("pg_mode") or "",
                page=request.form.get("page") or "1",
            )
        )

    @app.get("/spell/<int:spell_id>")
    def spell_detail(spell_id: int):
        spell = get_by_id(spell_id)
        if not spell:
            return ("Not found", 404)

        return render_template("spell_detail.html", spell=spell)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8090, debug=True)

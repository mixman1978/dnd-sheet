from __future__ import annotations

import json
from typing import Any
from flask import Flask, render_template, request, redirect, url_for, session

from engine.rules import (
    STATS, STAT_LABEL, CLASSES, LINEAGES, LINEAGE_BONUS, ALIGNMENTS, SKILLS
)
from engine.calc import (
    mod, prof_bonus, total_stats, hp_max, hit_die, class_skill_choices, saving_throws
)

DEFAULT_PG = {
    "nome": "Azir",
    "lineage": "Nessuno",
    "classe": "Warlock",
    "level": 1,
    "alignment": "Neutrale",
    "stats_base": {"for": 10, "des": 10, "cos": 10, "int": 10, "sag": 10, "car": 10},
    "lineage_extra_stats": [None, None],  # solo Mezzelfo
    "skills_proficient": [],
    "hp_current": 0,
    "hp_temp": 0,

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

def get_pg() -> dict:
    pg = session.get("pg")
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

    ensure_lineage_state(pg)
    return pg

def save_pg(pg: dict) -> None:
    session["pg"] = pg

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "dev-secret-key-change-me"

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
        st_prof = set(saving_throws(pg["classe"]))
        saving_rows = []
        for s in STATS:
            b = mod(totals[s]) + (pb if s in st_prof else 0)
            saving_rows.append({
                "stat": s,
                "label": STAT_LABEL[s],
                "bonus": b,
                "proficient": s in st_prof,
            })
        con_mod = mod(totals["cos"])
        hpmax = int(hp_max(pg["level"], pg["classe"], con_mod, "medio"))

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
            skill_rows.append({
                "name": sk,
                "stat": stat,
                "stat_label": STAT_LABEL[stat],
                "bonus": bonus_val,
                "proficient": proficient,
                "selectable": sk in allowed_skills,
            })
    
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
            STATS=STATS,
            STAT_LABEL=STAT_LABEL,
            CLASSES=CLASSES,
            LINEAGES=LINEAGES,
            ALIGNMENTS=ALIGNMENTS,
        )

    return app

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8090, debug=True)

from pathlib import Path
import json

from nicegui import app, ui
from fastapi.responses import FileResponse

from engine.rules import (
    STATS, STAT_LABEL, CLASSES, LINEAGES, LINEAGE_BONUS, ALIGNMENTS,
    SKILLS,
)
from engine.calc import (
    mod, prof_bonus, total_stats, hp_max, hit_die,
    spellcasting_ability, saving_throws, class_skill_choices,
)
from engine.storage import list_characters, load_character, save_character


# -------------------------
# Static files (FIX 404)
# -------------------------
BASE_DIR = Path(__file__).resolve().parent
app.add_static_files('/static', str(BASE_DIR / 'static'))


@app.get('/favicon.ico', include_in_schema=False)
def favicon_ico():
    return FileResponse(BASE_DIR / 'static' / 'favicon.ico')


@app.get('/apple-touch-icon.png', include_in_schema=False)
def apple_touch():
    return FileResponse(BASE_DIR / 'static' / 'apple-touch-icon.png')


DEFAULT_PG = {
    "nome": "Azir",
    "lineage": "Nessuno",
    "classe": "Warlock",
    "level": 1,
    "alignment": "Neutrale",
    "stats_base": {"for": 10, "des": 10, "cos": 10, "int": 10, "sag": 10, "car": 10},
    "hp_method": "medio",
    "hp_current": 0,
    "hp_temp": 0,
    "skills_proficient": [],
    "lineage_extra_stats": [None, None],
}


def _normalize_choice(value, options: list[str], default: str) -> str:
    if isinstance(value, str) and value in options:
        return value
    if isinstance(value, dict):
        for key in ("value", "label", "name_it", "name"):
            v = value.get(key)
            if isinstance(v, str) and v in options:
                return v
    return default


def new_pg() -> dict:
    # deep copy semplice e sicuro
    return json.loads(json.dumps(DEFAULT_PG, ensure_ascii=False))


@ui.page("/")
def index():
    ui.colors(primary="#1a1a1a")

    ui.add_head_html("""
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>
.sheet-title { font-variant: small-caps; letter-spacing: 0.08em; }
.sheet-label { font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; }
.sheet-value { font-size: 0.9rem; font-weight: 700; }
.tight { line-height: 1.05; }
.onepage-wrap { height: calc(100vh - 68px); overflow: hidden; }
.minh0 { min-height: 0; }
</style>
""")

    pg = new_pg()

    def ensure_lineage_state():
        # se non e' Mezzelfo, resettiamo le scelte extra
        if not str(pg.get("lineage", "")).startswith("Mezzelfo"):
            pg["lineage_extra_stats"] = [None, None]
            return

        v = pg.get("lineage_extra_stats")
        if not isinstance(v, list):
            pg["lineage_extra_stats"] = [None, None]
        else:
            while len(pg["lineage_extra_stats"]) < 2:
                pg["lineage_extra_stats"].append(None)
            pg["lineage_extra_stats"] = pg["lineage_extra_stats"][:2]

        allowed = [s for s in STATS if s != "car"]
        cleaned = []
        for st in pg["lineage_extra_stats"]:
            cleaned.append(st if st in allowed else None)
        pg["lineage_extra_stats"] = cleaned

    def get_lineage_bonus() -> dict:
        base_bonus = dict(LINEAGE_BONUS.get(pg.get("lineage"), {}) or {})
        if str(pg.get("lineage", "")).startswith("Mezzelfo"):
            extras = pg.get("lineage_extra_stats") or []
            allowed = {s for s in STATS if s != "car"}
            seen = set()
            for st in extras:
                if st in allowed and st not in seen:
                    base_bonus[st] = int(base_bonus.get(st, 0)) + 1
                    seen.add(st)
        return base_bonus

    # -------------------------
    # Sheet renderer
    # -------------------------
    @ui.refreshable
    def render_sheet():
        def refresh():
            render_sheet.refresh()

        base = pg["stats_base"]
        pg["lineage"] = _normalize_choice(pg.get("lineage"), LINEAGES, "Nessuno")
        pg["classe"] = _normalize_choice(pg.get("classe"), CLASSES, "Warlock")
        pg["alignment"] = _normalize_choice(pg.get("alignment"), ALIGNMENTS, "Neutrale")

        ensure_lineage_state()
        bonus = get_lineage_bonus()
        totals = total_stats(base, bonus)

        con_mod = mod(totals["cos"])
        pb = prof_bonus(pg["level"])

        # HP Max sempre calcolati in automatico
        hpmax_auto = int(hp_max(pg["level"], pg["classe"], con_mod, pg["hp_method"]))
        pg["hp_max"] = hpmax_auto

        # ---- Caratteristiche (orizzontale) ----
        ui.label("Caratteristiche").classes("sheet-title text-xs mb-1")
        with ui.element("div").classes("grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 w-full"):
            for s in STATS:
                with ui.card().classes("p-1"):
                    ui.label(STAT_LABEL[s]).classes("sheet-label")
                    with ui.row().classes("items-center justify-between"):
                        ui.number(
                            value=int(base[s]),
                            min=3,
                            max=20,
                            step=1,
                            on_change=lambda e, k=s: (
                                pg["stats_base"].__setitem__(k, int(e.value)),
                                refresh(),
                            ),
                        ).props('dense outlined input-class="text-sm text-right"').classes("w-16")
                        ui.label(f"Bonus {int(bonus.get(s, 0)):+d}").classes("text-[9px] text-gray-500")
                    ui.label(f"Tot {totals[s]}").classes("sheet-value")
                    ui.label(f"Mod {mod(totals[s]):+d}").classes("text-[10px] text-gray-600")

        # ---- Layout principale ----
        with ui.element("div").classes("w-full grid grid-cols-1 lg:grid-cols-[1fr_1fr_220px] gap-2 minh0"):
            # Colonna sinistra: Combattimento
            with ui.card().classes("p-1"):
                ui.label("Combattimento").classes("sheet-title text-xs mb-0")

                with ui.row().classes("w-full gap-2 flex-nowrap"):
                    with ui.card().classes("p-1 w-40"):
                        ui.label("Punti Ferita").classes("sheet-label")
                        ui.select(
                            ["medio", "tiro"],
                            value=pg["hp_method"],
                            on_change=lambda e: (pg.__setitem__("hp_method", e.value), refresh()),
                        ).props("dense outlined").classes("w-20")
                        ui.label(f"HP Max: {hpmax_auto}").classes("sheet-value")
                        with ui.row().classes("gap-1"):
                            ui.number(
                                value=int(pg["hp_current"]),
                                min=0,
                                step=1,
                                on_change=lambda e: pg.__setitem__("hp_current", int(e.value)),
                            ).props("dense outlined label='Attuali'").classes("w-16")
                            ui.number(
                                value=int(pg["hp_temp"]),
                                min=0,
                                step=1,
                                on_change=lambda e: pg.__setitem__("hp_temp", int(e.value)),
                            ).props("dense outlined label='Temp'").classes("w-16")

                    with ui.card().classes("p-1 w-40"):
                        ui.label("Dadi Vita").classes("sheet-label")
                        d = hit_die(pg["classe"])
                        ui.label(f"d{d} x {pg['level']}").classes("sheet-value")

                    abil = spellcasting_ability(pg["classe"])
                    if abil:
                        with ui.card().classes("p-1 w-40"):
                            ui.label("Incantatore").classes("sheet-label")
                            ui.label(f"Caratt: {STAT_LABEL[abil]}").classes("text-[10px] text-gray-500")
                            atk = pb + mod(totals[abil])
                            cd = 8 + pb + mod(totals[abil])
                            ui.label(f"Atk: {atk:+d}").classes("text-[10px] font-bold")
                            ui.label(f"CD: {cd}").classes("text-[10px] font-bold")

                ui.separator().classes("my-1")
                with ui.expansion("Attacchi e Incantesimi", value=False).classes("w-full"):
                    ui.textarea(value="", placeholder="Armi, attacchi, note...") \
                        .props("outlined rows=2") \
                        .classes("w-full")

            # Colonna centrale: Abilita
            with ui.card().classes("p-1"):
                ui.label("Abilita").classes("sheet-title text-xs mb-0")

                sc = class_skill_choices(pg["classe"]) or {}
                choose_n = int(sc.get("choose") or 0)
                allowed = sc.get("from") or sorted(SKILLS.keys())

                if "skills_proficient" not in pg or not isinstance(pg["skills_proficient"], list):
                    pg["skills_proficient"] = []
                pg["skills_proficient"] = [s for s in pg["skills_proficient"] if s in allowed]

                if choose_n and len(pg["skills_proficient"]) > choose_n:
                    pg["skills_proficient"] = pg["skills_proficient"][:choose_n]

                if choose_n:
                    ui.label(f"Scegli {choose_n} competenze").classes("text-[9px] text-gray-500")
                else:
                    ui.label("Selezione libera").classes("text-[9px] text-gray-500")

                sel_skills = ui.select(
                    allowed,
                    value=pg["skills_proficient"],
                    multiple=True,
                    label="Competenze",
                ).props("dense outlined").classes("w-full")

                def _on_skills_change(e):
                    new_val = list(e.args or [])
                    if choose_n and len(new_val) > choose_n:
                        new_val = new_val[:choose_n]
                        ui.notify(f"Puoi scegliere al massimo {choose_n} abilita", type="warning")
                        sel_skills.set_value(new_val)
                    pg["skills_proficient"] = new_val
                    refresh()

                sel_skills.on("update:model-value", _on_skills_change)

                ui.separator().classes("my-1")

                prof = set(pg["skills_proficient"])
                with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-1 w-full"):
                    for skill_name in sorted(SKILLS.keys()):
                        stat = SKILLS[skill_name]
                        b = mod(totals[stat]) + (pb if skill_name in prof else 0)
                        with ui.element("div").classes("p-1 border rounded"):
                            with ui.row().classes("items-center justify-between"):
                                ui.label(skill_name).classes("text-[10px]")
                                ui.label(STAT_LABEL[stat]).classes("text-[9px] text-gray-500")
                            with ui.row().classes("items-center justify-between"):
                                ui.label(f"{b:+d}").classes("text-[10px] font-bold")
                                if skill_name in prof:
                                    ui.icon("check").classes("text-green-600")
                                else:
                                    ui.label("").classes("w-4")

            # Colonna destra: TS + PB
            with ui.card().classes("p-1"):
                ui.label("Tiri Salvezza").classes("sheet-title text-xs mb-0")

                with ui.row().classes("w-full gap-1"):
                    with ui.card().classes("p-1 w-24"):
                        ui.label("Ispirazione").classes("sheet-label")
                        ui.select(["No", "Si"], value="No") \
                            .props("dense outlined") \
                            .classes("w-full")

                    with ui.card().classes("p-1 w-24"):
                        ui.label("Bonus Competenza").classes("sheet-label")
                        ui.label(f"+{pb}").classes("sheet-value")

                ui.separator().classes("my-1")

                st_prof = saving_throws(pg["classe"])
                pg["saving_throws_proficient"] = st_prof

                with ui.column().classes("gap-0.5"):
                    for s in STATS:
                        b = mod(totals[s]) + (pb if s in st_prof else 0)
                        with ui.row().classes("items-center justify-between tight"):
                            ui.label(STAT_LABEL[s]).classes("text-[10px]")
                            ui.label(f"{b:+d}").classes("text-[10px] font-bold")
                            if s in st_prof:
                                ui.icon("check").classes("text-green-600")
                            else:
                                ui.label("").classes("w-4")

    # -------------------------
    # Dialogs
    # -------------------------
    load_dialog = ui.dialog()
    with load_dialog, ui.card().classes("w-[520px]"):
        ui.label("Carica personaggio").classes("text-lg font-bold")
        sel = ui.select([], label="File").props("dense outlined").classes("w-full")

        load_dialog.on("show", lambda: sel.set_options(list_characters()))

        with ui.row().classes("justify-end gap-2"):
            ui.button("Annulla", on_click=load_dialog.close).props("outline")

            def do_load():
                if not sel.value:
                    ui.notify("Seleziona un file", type="warning")
                    return
                pg.update(load_character(sel.value))
                load_dialog.close()
                render_sheet.refresh()

            ui.button("Carica", on_click=do_load)

    import_dialog = ui.dialog()
    with import_dialog, ui.card().classes("w-[720px]"):
        ui.label("Import JSON").classes("text-lg font-bold")
        ta = ui.textarea(placeholder="Incolla qui JSON...").classes("w-full").props("outlined")

        with ui.row().classes("justify-end gap-2"):
            ui.button("Annulla", on_click=import_dialog.close).props("outline")

            def do_import():
                raw = (ta.value or "").strip()
                try:
                    data = json.loads(raw or "{}")
                    if not isinstance(data, dict):
                        raise ValueError("JSON deve essere un oggetto")
                except Exception:
                    ui.notify("JSON non valido", type="negative")
                    return
                pg.update(data)
                import_dialog.close()
                render_sheet.refresh()

            ui.button("Importa", on_click=do_import)

    export_dialog = ui.dialog()
    with export_dialog, ui.card().classes("w-[720px]"):
        ui.label("Export JSON").classes("text-lg font-bold")
        out = ui.textarea(value="").classes("w-full").props("outlined readonly")
        export_dialog.on("show", lambda: out.set_value(json.dumps(pg, ensure_ascii=False, indent=2)))

    # -------------------------
    # Header / Topbar
    # -------------------------
    with ui.header().classes("bg-[#1a1a1a] text-white"):
        with ui.row().classes("w-full items-center justify-between px-4"):
            with ui.row().classes("items-center gap-3 flex-nowrap"):
                ui.image("/static/logo.png").props("fit=contain").classes("h-auto w-40 shrink-0")
                menu_btn = ui.button(icon="menu").props("flat color=white")
                menu = ui.menu()

                with menu:
                    ui.menu_item("Nuovo", on_click=lambda: (pg.clear(), pg.update(new_pg()), render_sheet.refresh()))
                    ui.menu_item("Salva", on_click=lambda: ui.notify(
                        f"Salvato: {save_character(pg.get('nome','personaggio'), pg)}", type="positive"
                    ))
                    ui.menu_item("Carica", on_click=load_dialog.open)
                    ui.menu_item("Import", on_click=import_dialog.open)
                    ui.menu_item("Export", on_click=export_dialog.open)

                menu_btn.on("click", lambda: menu.open())

            with ui.row().classes("items-center gap-2 flex-nowrap"):
                ui.input(value=pg["nome"], placeholder="Nome PG") \
                    .props('dense outlined dark input-class="text-white"') \
                    .classes("w-36") \
                    .on("update:model-value", lambda e: pg.__setitem__("nome", e.args))

                ui.select(LINEAGES, value=pg["lineage"]) \
                    .props('dense outlined dark options-dense popup-content-class="bg-[#1a1a1a] text-white"') \
                    .classes("w-32") \
                    .on(
                        "update:model-value",
                        lambda e: (
                            pg.__setitem__("lineage", e.args),
                            ensure_lineage_state(),
                            render_sheet.refresh(),
                        ),
                    )

                if str(pg.get("lineage", "")).startswith("Mezzelfo"):
                    opts = {STAT_LABEL[s]: s for s in STATS if s != "car"}

                    def set_extra(idx: int, value: str | None):
                        ensure_lineage_state()
                        if value not in opts.values():
                            value = None
                        pg["lineage_extra_stats"][idx] = value
                        other_idx = 1 - idx
                        if pg["lineage_extra_stats"][other_idx] == value and value is not None:
                            pg["lineage_extra_stats"][other_idx] = None
                        render_sheet.refresh()

                    ui.select(
                        opts,
                        value=pg["lineage_extra_stats"][0],
                        label="+1 #1",
                    ).props('dense outlined dark options-dense popup-content-class="bg-[#1a1a1a] text-white"') \
                     .classes("w-20") \
                     .on("update:model-value", lambda e: set_extra(0, e.args))

                    ui.select(
                        opts,
                        value=pg["lineage_extra_stats"][1],
                        label="+1 #2",
                    ).props('dense outlined dark options-dense popup-content-class="bg-[#1a1a1a] text-white"') \
                     .classes("w-20") \
                     .on("update:model-value", lambda e: set_extra(1, e.args))

                ui.select(CLASSES, value=pg["classe"]) \
                    .props('dense outlined dark options-dense popup-content-class="bg-[#1a1a1a] text-white"') \
                    .classes("w-32") \
                    .on("update:model-value", lambda e: (pg.__setitem__("classe", e.args), render_sheet.refresh()))

                ui.number(value=pg["level"], min=1, max=20) \
                    .props('dense outlined dark input-class="text-white"') \
                    .classes("w-12") \
                    .on("update:model-value", lambda e: (pg.__setitem__("level", int(e.args or 1)), render_sheet.refresh()))

                ui.select(ALIGNMENTS, value=pg["alignment"]) \
                    .props('dense outlined dark options-dense popup-content-class="bg-[#1a1a1a] text-white"') \
                    .classes("w-32") \
                    .on("update:model-value", lambda e: pg.__setitem__("alignment", e.args))

    # -------------------------
    # Page content (no scroll pagina)
    # -------------------------
    with ui.column().classes("max-w-5xl mx-auto pt-1 px-3 pb-2 gap-1 items-start onepage-wrap minh0"):
        render_sheet()


ui.run(
    title="DnD Sheet",
    port=8090,
    reload=True,
    favicon=str(BASE_DIR / "static" / "favicon.ico"),
)

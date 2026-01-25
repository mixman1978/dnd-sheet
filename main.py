from pathlib import Path
import json

from nicegui import app, ui
from fastapi.responses import FileResponse

from engine.rules import (
    STATS, STAT_LABEL, CLASSES, LINEAGES, LINEAGE_BONUS, ALIGNMENTS,
    SAVING_THROWS_BY_CLASS, SKILLS, SPELLCASTING_ABILITY_BY_CLASS,
)
from engine.calc import mod, prof_bonus, total_stats, hp_max, spellcasting_ability
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
}


def new_pg() -> dict:
    # deep copy semplice e sicuro
    return json.loads(json.dumps(DEFAULT_PG, ensure_ascii=False))


@ui.page("/")
def index():
    ui.colors(primary="#0b1220")

    # Favicon + Apple Touch (Safari/iOS)
    ui.add_head_html("""
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
""")

    pg = new_pg()

    # -------------------------
    # Sheet renderer
    # -------------------------
    @ui.refreshable
    def render_sheet():
        base = pg["stats_base"]
        bonus = LINEAGE_BONUS.get(pg["lineage"], {})
        totals = total_stats(base, bonus)
        con_mod = mod(totals["cos"])
        pb = prof_bonus(pg["level"])

        ui.label("Caratteristiche").classes("text-2xl font-bold")

        with ui.row().classes("w-full gap-4 flex-wrap"):
            for s in STATS:
                with ui.card().classes("w-48"):
                    ui.label(STAT_LABEL[s]).classes("font-bold")
                    with ui.row().classes("items-center justify-between"):
                        ui.number(
                            value=int(base[s]),
                            min=3,
                            max=20,
                            step=1,
                            on_change=lambda e, k=s: (
                                pg["stats_base"].__setitem__(k, int(e.value)),
                                render_sheet.refresh(),
                            ),
                        ).props("dense outlined").classes("w-24")

                        ui.label(f"Tot {totals[s]}").classes("text-sm")

                    ui.label(f"Mod {mod(totals[s]):+d}").classes("text-lg font-bold")

        ui.separator()

        with ui.row().classes("w-full gap-6 flex-wrap items-start"):
            with ui.card().classes("w-80"):
                ui.label("Bonus Competenza").classes("font-bold")
                ui.label(f"+{pb}").classes("text-3xl font-bold")

            with ui.card().classes("w-80"):
                ui.label("Punti Ferita").classes("font-bold")
                with ui.row().classes("items-center gap-2"):
                    ui.select(
                        ["medio", "tiro"],
                        value=pg["hp_method"],
                        on_change=lambda e: (pg.__setitem__("hp_method", e.value), render_sheet.refresh()),
                    ).props("dense outlined").classes("w-32")

                    ui.button(
                        "Calcola HP Max",
                        on_click=lambda: (
                            pg.__setitem__(
                                "hp_max",
                                int(hp_max(pg["level"], pg["classe"], con_mod, pg["hp_method"])),
                            ),
                            render_sheet.refresh(),
                        ),
                    ).props("outline")

                hpmax = int(pg.get("hp_max", 0))
                ui.label(f"HP Max: {hpmax}").classes("text-lg font-bold")

                with ui.row().classes("gap-2"):
                    ui.number(
                        value=int(pg["hp_current"]),
                        min=0,
                        step=1,
                        on_change=lambda e: pg.__setitem__("hp_current", int(e.value)),
                    ).props("dense outlined label='Attuali'").classes("w-32")

                    ui.number(
                        value=int(pg["hp_temp"]),
                        min=0,
                        step=1,
                        on_change=lambda e: pg.__setitem__("hp_temp", int(e.value)),
                    ).props("dense outlined label='Temp'").classes("w-32")

            with ui.card().classes("w-80"):
                ui.label("Dadi Vita").classes("font-bold")
                d = {"Warlock": 8}.get(pg["classe"], 8)
                ui.label(f"d{d} × {pg['level']}").classes("text-lg font-bold")

        ui.separator()

        abil = spellcasting_ability(pg["classe"])
        if abil:
            with ui.card().classes("w-96"):
                ui.label("Incantatore").classes("font-bold")
                ui.label(f"Caratteristica: {STAT_LABEL[abil]}").classes("text-sm")
                atk = pb + mod(totals[abil])
                cd = 8 + pb + mod(totals[abil])
                ui.label(f"Attacco Incantesimi: {atk:+d}").classes("text-lg font-bold")
                ui.label(f"CD Incantesimi: {cd}").classes("text-lg font-bold")

        with ui.expansion("Debug JSON", icon="code").classes("w-full"):
            ui.code(json.dumps(pg, ensure_ascii=False, indent=2), language="json")

    # -------------------------
    # Dialogs
    # -------------------------
    load_dialog = ui.dialog()
    with load_dialog, ui.card().classes("w-[520px]"):
        ui.label("Carica personaggio").classes("text-lg font-bold")
        sel = ui.select([], label="File").props("dense outlined").classes("w-full")

        # Aggiorna sempre la lista quando apri il dialog
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
    with ui.header().classes("bg-[#0b1220] text-white"):
        with ui.row().classes("w-full items-center justify-between px-4"):
            with ui.row().classes("items-center gap-3"):
                ui.image("/static/logo_dark.png").props("fit=contain").style("height:28px; display:block;")

                menu_btn = ui.button(icon="menu").props("flat color=white")
                menu = ui.menu()

                with menu:
                    ui.menu_item("✨ Nuovo", on_click=lambda: (pg.clear(), pg.update(new_pg()), render_sheet.refresh()))
                    ui.menu_item("💾 Salva", on_click=lambda: ui.notify(
                        f"Salvato: {save_character(pg.get('nome','personaggio'), pg)}", type="positive"
                    ))
                    ui.menu_item("📂 Carica", on_click=load_dialog.open)
                    ui.menu_item("⬆ Import", on_click=import_dialog.open)
                    ui.menu_item("⬇ Export", on_click=export_dialog.open)

                menu_btn.on("click", lambda: menu.open())

            with ui.row().classes("items-center gap-2 flex-wrap justify-end"):
                ui.input(
                    value=pg["nome"],
                    placeholder="Nome PG",
                ).props('dense outlined dark input-class="text-white"').classes("w-48") \
                 .on("update:model-value", lambda e: pg.__setitem__("nome", e.value))

                ui.select(
                    LINEAGES,
                    value=pg["lineage"],
                ).props('dense outlined dark options-dense popup-content-class="bg-[#0b1220] text-white"') \
                 .classes("w-52") \
                 .on("update:model-value", lambda e: (pg.__setitem__("lineage", e.value), render_sheet.refresh()))

                ui.select(
                    CLASSES,
                    value=pg["classe"],
                ).props('dense outlined dark options-dense popup-content-class="bg-[#0b1220] text-white"') \
                 .classes("w-44") \
                 .on("update:model-value", lambda e: (pg.__setitem__("classe", e.value), render_sheet.refresh()))

                ui.number(
                    value=pg["level"],
                    min=1,
                    max=20,
                ).props('dense outlined dark input-class="text-white"').classes("w-24") \
                 .on("update:model-value", lambda e: (pg.__setitem__("level", int(e.value or 1)), render_sheet.refresh()))

                ui.select(
                    ALIGNMENTS,
                    value=pg["alignment"],
                ).props('dense outlined dark options-dense popup-content-class="bg-[#0b1220] text-white"') \
                 .classes("w-56") \
                 .on("update:model-value", lambda e: pg.__setitem__("alignment", e.value))

    # -------------------------
    # Page content
    # -------------------------
    with ui.column().classes("max-w-6xl mx-auto pt-2 px-6 pb-6 gap-4 items-start"):
        render_sheet()


# favicon: usa il file reale sul disco (più affidabile)
ui.run(
    title="DnD Sheet",
    port=8090,
    reload=True,
    favicon=str(BASE_DIR / "static" / "favicon.ico"),
)

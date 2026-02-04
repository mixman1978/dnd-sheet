import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from engine.db import connect, ensure_schema
from engine.spells_repo import search_spells


class SpellsPgLimitsTests(unittest.TestCase):
    def test_ranger_5_has_max_spell_level_2(self):
        pg = {"classe": "Ranger", "level": 5}
        with patch("app._class_code_from_name_it", return_value="ranger"):
            allowed, max_spell_level, _labels = app_module._compute_pg_spell_limits(pg)
        self.assertEqual({"ranger"}, allowed)
        self.assertEqual(2, max_spell_level)

    def test_wizard_5_has_max_spell_level_3(self):
        pg = {"classe": "Mago", "level": 5}
        with patch("app._class_code_from_name_it", return_value="wizard"):
            allowed, max_spell_level, _labels = app_module._compute_pg_spell_limits(pg)
        self.assertEqual({"wizard"}, allowed)
        self.assertEqual(3, max_spell_level)

    def test_toggle_off_keeps_existing_search_behavior(self):
        flask_app = app_module.create_app()
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as client, patch("app.get_pg", return_value={"classe": "Ranger", "level": 5}), patch(
            "app._current_session_character_id", return_value=123
        ), patch("app.search_spells", return_value=[]) as search_mock, patch(
            "app.list_character_spells", return_value=[]
        ), patch("app.list_characters", return_value=[]), patch("app.render_template", return_value="ok"):
            response = client.get("/spells?q=freccia")

        self.assertEqual(200, response.status_code)
        kwargs = search_mock.call_args.kwargs
        self.assertIsNone(kwargs["class_codes"])
        self.assertIsNone(kwargs["max_level"])
        self.assertIsNone(kwargs["class_code"])
        self.assertFalse(kwargs["ritual_only"])
        self.assertFalse(kwargs["concentration_only"])

    def test_ritual_only_filter_returns_only_ritual_spells(self):
        results = search_spells(q="", ritual_only=True, limit=50, offset=0)
        self.assertGreater(len(results), 0)
        ids = [int(item["id"]) for item in results]
        placeholders = ", ".join("?" for _ in ids)
        with connect() as conn:
            ensure_schema(conn)
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM spells WHERE id IN ({placeholders}) AND ritual = 0",
                ids,
            ).fetchone()
        self.assertEqual(0, int(row["cnt"]))

    def test_concentration_only_with_invis_includes_invisibilita_superiore(self):
        results = search_spells(q="invis", concentration_only=True, limit=50, offset=0)
        self.assertGreater(len(results), 0)
        names = [str(item["name"]).lower() for item in results]
        self.assertTrue(any("invisibilit" in name and "superiore" in name for name in names))
        ids = [int(item["id"]) for item in results]
        placeholders = ", ".join("?" for _ in ids)
        with connect() as conn:
            ensure_schema(conn)
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM spells WHERE id IN ({placeholders}) AND concentration = 0",
                ids,
            ).fetchone()
        self.assertEqual(0, int(row["cnt"]))

    def test_individuazione_del_magico_has_ritual_flag(self):
        results = search_spells(q="individuazione del magico", limit=50, offset=0)
        self.assertGreater(len(results), 0)
        target = next((sp for sp in results if "individuazione del magico" in str(sp["name"]).lower()), None)
        self.assertIsNotNone(target)
        self.assertTrue(bool(target["ritual"]))

    def test_invisibilita_superiore_has_concentration_flag(self):
        results = search_spells(q="invis", limit=100, offset=0)
        self.assertGreater(len(results), 0)
        target = next((sp for sp in results if "invisibilit" in str(sp["name"]).lower() and "superiore" in str(sp["name"]).lower()), None)
        self.assertIsNotNone(target)
        self.assertTrue(bool(target["concentration"]))

    def test_clear_spells_filters_script_resets_new_checkboxes(self):
        text = Path("templates/spells.html").read_text(encoding="utf-8")
        self.assertIn("if (ritualOnlyInput) ritualOnlyInput.checked = false;", text)
        self.assertIn("if (concentrationOnlyInput) concentrationOnlyInput.checked = false;", text)
        self.assertIn("hasRitualOnly", text)
        self.assertIn("hasConcentrationOnly", text)
        self.assertIn('title="Rituale"', text)
        self.assertIn('title="Concentrazione"', text)


if __name__ == "__main__":
    unittest.main()

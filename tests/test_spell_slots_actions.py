import unittest
from unittest.mock import patch

import app as app_module


class SpellSlotsActionsTests(unittest.TestCase):
    def setUp(self):
        self.flask_app = app_module.create_app()
        self.flask_app.config["TESTING"] = True

    def _seed_session_pg(self, client, pg: dict) -> None:
        with client.session_transaction() as sess:
            sess["pg"] = pg

    def test_update_standard_slot_decrements_and_clamps(self):
        pg = {
            "nome": "Tester",
            "classe": "Druido",
            "level": 3,
            "spell_slots_max": {"1": 4, "2": 2},
            "spell_slots_current": {"1": 4, "2": 1},
            "pact_slots_max": 0,
            "pact_slots_current": 0,
            "pact_slot_level": 0,
        }
        with self.flask_app.test_client() as client, patch("app.save_character_to_db", return_value=1), patch(
            "app._current_session_character_id", return_value=1
        ):
            self._seed_session_pg(client, pg)
            resp = client.post(
                "/character/spell_slots/update",
                data={
                    "character_id": "1",
                    "slot_type": "standard",
                    "slot_level": "2",
                    "delta": "-1",
                    "next": "/",
                },
            )
            self.assertEqual(302, resp.status_code)
            with client.session_transaction() as sess:
                updated = sess["pg"]
            self.assertEqual(0, int(updated["spell_slots_current"]["2"]))

    def test_rest_short_resets_only_pact(self):
        pg = {
            "nome": "Tester",
            "classe": "Warlock",
            "level": 3,
            "spell_slots_max": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "spell_slots_current": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "pact_slots_max": 2,
            "pact_slots_current": 0,
            "pact_slot_level": 2,
        }
        with self.flask_app.test_client() as client, patch("app.save_character_to_db", return_value=1), patch(
            "app._current_session_character_id", return_value=1
        ):
            self._seed_session_pg(client, pg)
            resp = client.post(
                "/character/spell_slots/rest",
                data={"character_id": "1", "rest_type": "short", "next": "/"},
            )
            self.assertEqual(302, resp.status_code)
            with client.session_transaction() as sess:
                updated = sess["pg"]
            self.assertEqual(2, int(updated["pact_slots_current"]))
            self.assertEqual(0, int(updated["spell_slots_current"]["1"]))

    def test_rest_long_resets_standard_and_pact(self):
        pg = {
            "nome": "Tester",
            "classe": "Druido",
            "level": 3,
            "classes": [{"code": "druid", "level": 3}, {"code": "warlock", "level": 3}],
            "spell_slots_max": {"1": 4, "2": 2, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "spell_slots_current": {"1": 1, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "pact_slots_max": 2,
            "pact_slots_current": 0,
            "pact_slot_level": 2,
        }
        with self.flask_app.test_client() as client, patch("app.save_character_to_db", return_value=1), patch(
            "app._current_session_character_id", return_value=1
        ):
            self._seed_session_pg(client, pg)
            resp = client.post(
                "/character/spell_slots/rest",
                data={"character_id": "1", "rest_type": "long", "next": "/"},
            )
            self.assertEqual(302, resp.status_code)
            with client.session_transaction() as sess:
                updated = sess["pg"]
            self.assertEqual(4, int(updated["spell_slots_current"]["1"]))
            self.assertEqual(2, int(updated["spell_slots_current"]["2"]))
            self.assertEqual(2, int(updated["pact_slots_current"]))

    def test_consume_spell_slot_prefers_standard_then_pact(self):
        pg = {
            "spell_slots_max": {"1": 4, "2": 2, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "spell_slots_current": {"1": 1, "2": 1, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "pact_slots_max": 2,
            "pact_slots_current": 2,
            "pact_slot_level": 2,
        }
        ok, _detail = app_module._consume_spell_slot(pg, 2)
        self.assertTrue(ok)
        self.assertEqual(0, int(pg["spell_slots_current"]["2"]))
        self.assertEqual(2, int(pg["pact_slots_current"]))

    def test_consume_spell_slot_falls_back_to_pact(self):
        pg = {
            "spell_slots_max": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "spell_slots_current": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "pact_slots_max": 2,
            "pact_slots_current": 1,
            "pact_slot_level": 3,
        }
        ok, _detail = app_module._consume_spell_slot(pg, 2)
        self.assertTrue(ok)
        self.assertEqual(0, int(pg["pact_slots_current"]))

    def test_available_cast_levels_includes_depleted_levels_as_zero(self):
        pg = {
            "spell_slots_max": {"1": 4, "2": 2, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "spell_slots_current": {"1": 0, "2": 1, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "pact_slots_max": 0,
            "pact_slots_current": 0,
            "pact_slot_level": 0,
        }
        levels = app_module._available_cast_levels_for_spell(pg, 1)
        by_level = {int(x["level"]): int(x["remaining"]) for x in levels}
        self.assertEqual(0, by_level[1])
        self.assertEqual(1, by_level[2])
        long_entries = [x for x in levels if x["rest"] == "long"]
        self.assertGreaterEqual(len(long_entries), 2)

    def test_consume_by_level_choice_prefers_standard_then_pact(self):
        pg = {
            "spell_slots_max": {"1": 0, "2": 1, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "spell_slots_current": {"1": 0, "2": 1, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0},
            "pact_slots_max": 2,
            "pact_slots_current": 2,
            "pact_slot_level": 2,
        }
        ok, _detail = app_module._consume_spell_slot_by_choice(pg, 2, "standard:2")
        self.assertTrue(ok)
        self.assertEqual(0, int(pg["spell_slots_current"]["2"]))
        self.assertEqual(2, int(pg["pact_slots_current"]))


if __name__ == "__main__":
    unittest.main()

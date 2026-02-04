import unittest

import app as app_module


class SpellSlotsTests(unittest.TestCase):
    def test_druid_3_slots(self):
        pg = {"classes": [{"code": "druid", "level": 3}]}
        app_module.recalc_spell_slots(pg)
        self.assertEqual(4, pg["spell_slots_max"]["1"])
        self.assertEqual(2, pg["spell_slots_max"]["2"])

    def test_ranger_5_single_class_uses_half_caster_table(self):
        pg = {"classes": [{"code": "ranger", "level": 5}]}
        app_module.recalc_spell_slots(pg)
        self.assertEqual(4, pg["spell_slots_max"]["1"])
        self.assertEqual(2, pg["spell_slots_max"]["2"])

    def test_warlock_3_pact_slots(self):
        pg = {"classes": [{"code": "warlock", "level": 3}]}
        app_module.recalc_spell_slots(pg)
        self.assertEqual(2, pg["pact_slots_max"])
        self.assertEqual(2, pg["pact_slot_level"])
        self.assertEqual(2, pg["pact_slots_current"])

    def test_wizard_5_slots(self):
        pg = {"classes": [{"code": "wizard", "level": 5}]}
        app_module.recalc_spell_slots(pg)
        self.assertEqual(4, pg["spell_slots_max"]["1"])
        self.assertEqual(3, pg["spell_slots_max"]["2"])
        self.assertEqual(2, pg["spell_slots_max"]["3"])

    def test_multiclass_uses_multiclass_caster_level_rule(self):
        pg = {"classes": [{"code": "ranger", "level": 5}, {"code": "cleric", "level": 1}]}
        app_module.recalc_spell_slots(pg)
        self.assertEqual(4, pg["spell_slots_max"]["1"])
        self.assertEqual(2, pg["spell_slots_max"]["2"])
        self.assertEqual(0, pg["spell_slots_max"]["3"])


if __name__ == "__main__":
    unittest.main()

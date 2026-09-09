"""Loading, validation, and recovery from damaged saves."""

import json
import unittest
from pathlib import Path

from detective_x.engine.loader import load_all, load_case_dict, load_case_file, validate
from detective_x.exceptions import CaseDataError, CorruptSaveError, SaveVersionError
from detective_x.models.case import Case
from detective_x.persistence.save_manager import (
    FileStorage,
    MemoryStorage,
    SaveManager,
)

FIXTURES = Path(__file__).parent / "fixtures"
CASE_DIR = Path(__file__).parent.parent / "detective_x" / "data" / "cases"


def good_case() -> dict:
    return json.loads((CASE_DIR / "case_001.json").read_text(encoding="utf-8"))


class TestCaseLoading(unittest.TestCase):
    def test_all_cases_load(self):
        cases = load_all()
        self.assertGreaterEqual(len(cases), 15)
        self.assertTrue(all(isinstance(c, Case) for c in cases))

    def test_case_ids_are_unique(self):
        ids = [c.id for c in load_all()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_missing_file_raises_case_data_error_not_file_not_found(self):
        with self.assertRaises(CaseDataError):
            load_case_file(CASE_DIR / "case_999.json")

    def test_malformed_json_raises_case_data_error(self):
        broken = FIXTURES / "corrupt_save.json"
        with self.assertRaises(CaseDataError):
            load_case_file(broken)

    def test_missing_field_names_the_field(self):
        raw = good_case()
        del raw["culprit_id"]
        with self.assertRaises(CaseDataError) as ctx:
            load_case_dict(raw)
        self.assertIn("culprit_id", str(ctx.exception))


class TestValidation(unittest.TestCase):
    def test_culprit_must_be_a_suspect(self):
        raw = good_case()
        raw["culprit_id"] = "nobody"
        with self.assertRaises(CaseDataError) as ctx:
            load_case_dict(raw)
        self.assertIn("not a suspect", str(ctx.exception))

    def test_evidence_cannot_implicate_an_unknown_suspect(self):
        raw = good_case()
        raw["evidence"][0]["implicates"] = "ghost"
        with self.assertRaises(CaseDataError):
            load_case_dict(raw)

    def test_prerequisites_must_exist(self):
        raw = good_case()
        raw["evidence"][0]["requires"] = ["e999"]
        with self.assertRaises(CaseDataError):
            load_case_dict(raw)

    def test_reliability_must_be_in_range(self):
        raw = good_case()
        raw["evidence"][0]["reliability"] = 140
        with self.assertRaises(CaseDataError):
            load_case_dict(raw)

    def test_unknown_difficulty_is_rejected(self):
        raw = good_case()
        raw["difficulty"] = "Impossible"
        with self.assertRaises(CaseDataError):
            load_case_dict(raw)

    def test_a_case_with_no_clue_against_the_culprit_is_unsolvable(self):
        raw = good_case()
        for ev in raw["evidence"]:
            if ev.get("implicates") == raw["culprit_id"]:
                ev["implicates"] = None
        with self.assertRaises(CaseDataError) as ctx:
            load_case_dict(raw)
        self.assertIn("unsolvable", str(ctx.exception))

    def test_unreachable_clue_is_rejected(self):
        raw = good_case()
        raw["locations"][0]["searchables"] = []
        with self.assertRaises(CaseDataError) as ctx:
            load_case_dict(raw)
        self.assertIn("never be found", str(ctx.exception))

    def test_every_shipped_case_passes_validation(self):
        for case in load_all():
            validate(case)


class TestSaves(unittest.TestCase):
    def test_round_trip(self):
        mgr = SaveManager(MemoryStorage())
        from detective_x.models.case import Detective

        original = Detective(name="Ada", xp=900, cases_won=3, completed={1, 2})
        mgr.save_profile(original)
        restored = mgr.load_profile()
        self.assertEqual(restored.name, "Ada")
        self.assertEqual(restored.xp, 900)
        self.assertEqual(restored.completed, {1, 2})

    def test_absent_save_returns_none_rather_than_raising(self):
        self.assertIsNone(SaveManager(MemoryStorage()).load_profile())

    def test_corrupt_save_raises_a_named_error(self):
        storage = MemoryStorage()
        storage.write("profile", (FIXTURES / "corrupt_save.json").read_text())
        with self.assertRaises(CorruptSaveError):
            SaveManager(storage).load_profile()

    def test_the_program_recovers_from_a_corrupt_save(self):
        storage = MemoryStorage()
        storage.write("profile", (FIXTURES / "corrupt_save.json").read_text())
        mgr = SaveManager(storage)
        with self.assertRaises(CorruptSaveError):
            mgr.load_profile()
        mgr.recover("profile")
        self.assertIsNone(mgr.load_profile())  # cleared, and no crash

    def test_a_newer_schema_is_refused_clearly(self):
        storage = MemoryStorage()
        storage.write("profile", (FIXTURES / "future_save.json").read_text())
        with self.assertRaises(SaveVersionError):
            SaveManager(storage).load_profile()

    def test_a_save_with_no_version_marker_is_refused(self):
        storage = MemoryStorage()
        storage.write("profile", json.dumps({"detective": {"name": "x"}}))
        with self.assertRaises(CorruptSaveError):
            SaveManager(storage).load_profile()

    def test_file_storage_writes_atomically_and_keeps_a_backup(self):
        import tempfile
        from detective_x.models.case import Detective

        with tempfile.TemporaryDirectory() as tmp:
            mgr = SaveManager(FileStorage(Path(tmp)))
            mgr.save_profile(Detective(name="First", xp=10))
            mgr.save_profile(Detective(name="Second", xp=20))
            self.assertEqual(mgr.load_profile().name, "Second")
            self.assertIn("First", mgr.storage.backup("profile"))
            self.assertFalse(list(Path(tmp).glob("*.tmp")), "temp files left behind")

    def test_backup_is_restored_when_the_live_save_is_damaged(self):
        import tempfile
        from detective_x.models.case import Detective

        with tempfile.TemporaryDirectory() as tmp:
            storage = FileStorage(Path(tmp))
            mgr = SaveManager(storage)
            mgr.save_profile(Detective(name="Good", xp=55))
            mgr.save_profile(Detective(name="AlsoGood", xp=66))
            (Path(tmp) / "profile.json").write_text("{ not json", encoding="utf-8")
            with self.assertRaises(CorruptSaveError):
                mgr.load_profile()
            self.assertTrue(mgr.recover("profile"))
            self.assertEqual(mgr.load_profile().name, "Good")


if __name__ == "__main__":
    unittest.main()

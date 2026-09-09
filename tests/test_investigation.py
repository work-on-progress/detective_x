"""The investigation session: the stateful layer both front-ends drive."""

import unittest

from detective_x.engine.analyst import DeductionEngine
from detective_x.engine.investigation import Investigation
from detective_x.engine.loader import load_all
from detective_x.exceptions import InvalidChoice
from detective_x.models.enums import CaseStatus, Difficulty


class TestInvestigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_all()
        cls.analyst = DeductionEngine(cls.cases)

    def fresh(self, index=0, **kw):
        return Investigation(self.cases[index], analyst=self.analyst, seed=7, **kw)

    def test_a_new_investigation_starts_empty(self):
        inv = self.fresh()
        self.assertEqual(inv.state.score, 0)
        self.assertEqual(inv.state.found_evidence, set())
        self.assertIs(inv.state.status, CaseStatus.IN_PROGRESS)

    def test_searching_yields_evidence_and_score(self):
        inv = self.fresh()
        case = inv.case
        loc = case.locations[0]
        target = next(s for s in loc.searchables if s.yields)
        before = inv.state.score
        result = inv.search(loc.id, target.id)
        self.assertTrue(result["found"])
        self.assertGreater(inv.state.score, before)

    def test_searching_the_same_place_twice_costs_points(self):
        inv = self.fresh()
        loc = inv.case.locations[0]
        target = next(s for s in loc.searchables if s.yields)
        inv.search(loc.id, target.id)
        mid = inv.state.score
        result = inv.search(loc.id, target.id)
        self.assertTrue(result["repeat"])
        self.assertLess(inv.state.score, mid)

    def test_an_unknown_searchable_is_rejected(self):
        inv = self.fresh()
        with self.assertRaises(InvalidChoice):
            inv.search(inv.case.locations[0].id, "nonexistent")

    def test_score_cannot_be_driven_below_zero(self):
        inv = self.fresh()
        loc = inv.case.locations[0]
        target = loc.searchables[0]
        for _ in range(60):
            inv.search(loc.id, target.id)
        self.assertGreaterEqual(inv.state.score, 0)

    def test_locked_questions_cannot_be_asked_early(self):
        inv = self.fresh()
        for suspect in inv.case.suspects:
            for st in suspect.statements:
                if st.unlocked_by and st.unlocked_by not in inv.state.found_evidence:
                    with self.assertRaises(InvalidChoice):
                        inv.ask(suspect.id, st.topic)
                    return
        self.skipTest("no gated statements in the first case")

    def test_evidence_chains_resolve_automatically(self):
        inv = self.fresh()
        chained = [ev for ev in inv.case.evidence if ev.requires]
        self.assertTrue(chained, "the first case should have a chain")
        for loc in inv.case.locations:
            for s in loc.searchables:
                inv.search(loc.id, s.id)
        for ev in chained:
            self.assertIn(ev.id, inv.state.found_evidence)

    def test_expert_difficulty_hides_the_meter(self):
        expert = next(c for c in self.cases if c.difficulty is Difficulty.EXPERT)
        inv = Investigation(expert, analyst=self.analyst, seed=7)
        self.assertFalse(inv.dashboard()["shows_meter"])
        self.assertTrue(all(s["suspicion"] is None for s in inv.suspects()))

    def test_hints_are_finite_and_cost_points(self):
        inv = self.fresh()
        inv.state.score = 500
        allowance = inv.state.hints_remaining
        for _ in range(allowance):
            self.assertTrue(inv.hint()["available"])
        self.assertFalse(inv.hint()["available"])
        self.assertLess(inv.state.score, 500)

    def test_accusing_the_culprit_solves_the_case(self):
        inv = self.fresh()
        result = inv.accuse(inv.case.culprit_id)
        self.assertTrue(result["solved"])
        self.assertIs(inv.state.status, CaseStatus.SOLVED)

    def test_accusing_the_wrong_person_fails_and_lists_what_was_missed(self):
        inv = self.fresh()
        wrong = next(s for s in inv.case.suspects if s.id != inv.case.culprit_id)
        result = inv.accuse(wrong.id)
        self.assertFalse(result["solved"])
        self.assertIs(inv.state.status, CaseStatus.FAILED)
        self.assertTrue(result["missed"])

    def test_state_survives_a_round_trip(self):
        from detective_x.models.case import InvestigationState

        inv = self.fresh()
        loc = inv.case.locations[0]
        inv.search(loc.id, loc.searchables[0].id)
        snapshot = InvestigationState.from_dict(inv.snapshot())
        self.assertEqual(snapshot.found_evidence, inv.state.found_evidence)
        self.assertEqual(snapshot.score, inv.state.score)
        self.assertEqual(snapshot.difficulty, inv.state.difficulty)

    def test_every_case_can_be_played_to_a_correct_solution(self):
        """A full playthrough of all fifteen cases, driven through the engine."""
        for index, case in enumerate(self.cases):
            inv = Investigation(case, analyst=self.analyst, seed=3)
            for loc in case.locations:
                for s in loc.searchables:
                    inv.search(loc.id, s.id)
            for suspect in case.suspects:
                for st in suspect.available_statements(inv.state.found_evidence):
                    inv.ask(suspect.id, st.topic)
            self.assertEqual(
                len(inv.state.found_evidence), case.total_evidence, case.title
            )
            result = inv.accuse(case.culprit_id)
            self.assertTrue(result["solved"], case.title)
            self.assertGreaterEqual(result["stars"], 3, f"{case.title}: {result}")


class TestEngineIsHeadless(unittest.TestCase):
    """The layer rule, enforced by a test rather than by good intentions."""

    def test_no_engine_module_prints_or_reads_input(self):
        import pathlib

        root = pathlib.Path(__file__).parent.parent / "detective_x"
        offenders = []
        for path in list((root / "engine").rglob("*.py")) + list((root / "models").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for token in ("print(", "input("):
                if token in source:
                    offenders.append(f"{path.name}: {token}")
        self.assertEqual(offenders, [], f"engine layer must not do I/O: {offenders}")

    def test_engine_does_not_import_the_ui(self):
        import pathlib

        root = pathlib.Path(__file__).parent.parent / "detective_x"
        offenders = []
        for path in list((root / "engine").rglob("*.py")) + list((root / "models").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "from ..ui" in source or "import ui" in source:
                offenders.append(path.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

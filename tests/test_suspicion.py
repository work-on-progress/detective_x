"""Suspicion scoring, red herrings, and the guarantee that cases are solvable."""

import unittest

from detective_x.config import CONTRADICTION_PENALTY
from detective_x.engine.deduction import (
    compute_suspicion,
    find_contradictions,
    newly_unlocked,
    raw_suspicion,
)
from detective_x.engine.loader import load_all


class TestSuspicion(unittest.TestCase):
    def setUp(self):
        self.cases = load_all()

    def test_scores_are_clamped(self):
        for case in self.cases:
            full = {ev.id for ev in case.evidence}
            scores = compute_suspicion(case, full, find_contradictions(case, full))
            for sid, value in scores.items():
                self.assertGreaterEqual(value, 0, f"{case.title}/{sid}")
                self.assertLessEqual(value, 100, f"{case.title}/{sid}")

    def test_every_suspect_is_scored(self):
        for case in self.cases:
            scores = compute_suspicion(case, set(), set())
            self.assertEqual(set(scores), {s.id for s in case.suspects}, case.title)

    def test_no_evidence_means_base_suspicion_only(self):
        for case in self.cases:
            scores = compute_suspicion(case, set(), set())
            for suspect in case.suspects:
                self.assertEqual(scores[suspect.id], min(100, suspect.base_suspicion))

    def test_reliability_scales_the_contribution(self):
        """A less reliable clue must move the needle less than a certain one."""
        checked = 0
        for case in self.cases:
            for ev in case.evidence:
                if ev.weight >= 10 and ev.reliability <= 90:
                    checked += 1
                    self.assertLess(ev.effective_weight, ev.weight, f"{case.title}/{ev.id}")
        self.assertGreater(checked, 20, "the corpus should exercise reliability")

    def test_a_contradiction_adds_the_fixed_penalty(self):
        case = self.cases[0]
        sid = case.suspects[0].id
        base = compute_suspicion(case, set(), set())[sid]
        with_c = compute_suspicion(case, set(), {f"{sid}:anything"})[sid]
        self.assertEqual(with_c, min(100, base + CONTRADICTION_PENALTY))

    def test_a_cleared_red_herring_stops_counting(self):
        checked = 0
        for case in self.cases:
            for ev in case.evidence:
                if not (ev.is_red_herring and ev.cleared_by and ev.implicates):
                    continue
                checked += 1
                without = compute_suspicion(case, {ev.id}, set())[ev.implicates]
                with_clear = compute_suspicion(case, {ev.id, ev.cleared_by}, set())[ev.implicates]
                self.assertLess(with_clear, without, f"{case.title}/{ev.id}")
        self.assertGreater(checked, 10, "the corpus should exercise red herrings")

    def test_red_herrings_never_point_at_the_real_culprit(self):
        for case in self.cases:
            for ev in case.evidence:
                if ev.is_red_herring:
                    self.assertNotEqual(ev.implicates, case.culprit_id, case.title)


class TestSolvability(unittest.TestCase):
    """The test that matters most: no case can trap a player."""

    def setUp(self):
        self.cases = load_all()

    def test_full_evidence_makes_the_culprit_the_clear_leader(self):
        for case in self.cases:
            full = {ev.id for ev in case.evidence}
            scores = raw_suspicion(case, full, find_contradictions(case, full))
            top = max(scores.values())
            leaders = [sid for sid, v in scores.items() if v == top]
            self.assertEqual(leaders, [case.culprit_id],
                             f"{case.title}: {scores}")

    def test_the_culprit_leads_by_a_real_margin(self):
        for case in self.cases:
            full = {ev.id for ev in case.evidence}
            scores = raw_suspicion(case, full, find_contradictions(case, full))
            ordered = sorted(scores.values(), reverse=True)
            self.assertGreaterEqual(ordered[0] - ordered[1], 25, case.title)

    def test_every_clue_is_reachable(self):
        for case in self.cases:
            reachable = {
                eid for loc in case.locations for sr in loc.searchables for eid in sr.yields
            }
            chained = {ev.id for ev in case.evidence if ev.requires}
            for ev in case.evidence:
                self.assertIn(ev.id, reachable | chained, f"{case.title}/{ev.id}")

    def test_evidence_chains_terminate(self):
        for case in self.cases:
            reachable = {
                eid for loc in case.locations for sr in loc.searchables for eid in sr.yields
            }
            held, guard = set(reachable), 0
            while (fresh := newly_unlocked(case, held)):
                held |= fresh
                guard += 1
                self.assertLess(guard, 40, f"{case.title}: chain does not terminate")
            self.assertEqual(held, {ev.id for ev in case.evidence}, case.title)


if __name__ == "__main__":
    unittest.main()

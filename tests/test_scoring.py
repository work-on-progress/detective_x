"""Scoring is pure arithmetic, so it is tested directly."""

import unittest

from detective_x.config import SCORE_TABLE
from detective_x.engine import scoring
from detective_x.engine.loader import load_all
from detective_x.exceptions import UnknownScoreAction
from detective_x.models.enums import Difficulty


class TestApply(unittest.TestCase):
    def test_known_action_applies_its_value(self):
        self.assertEqual(scoring.apply(100, "evidence_found"), 130)

    def test_repeated_application(self):
        self.assertEqual(scoring.apply(0, "hint_used", 3), 0)
        self.assertEqual(scoring.apply(200, "hint_used", 3), 50)

    def test_score_never_goes_negative(self):
        self.assertEqual(scoring.apply(10, "wrong_accusation"), 0)

    def test_unknown_action_raises(self):
        with self.assertRaises(UnknownScoreAction):
            scoring.apply(100, "bribe_the_witness")

    def test_one_hint_costs_fifty_three_cost_one_fifty(self):
        self.assertEqual(scoring.apply(500, "hint_used"), 450)
        self.assertEqual(scoring.apply(500, "hint_used", 3), 350)


class TestStars(unittest.TestCase):
    def test_perfect_run_earns_five(self):
        self.assertEqual(scoring.star_rating(1000, 1000), 5)

    def test_poor_run_earns_one(self):
        self.assertEqual(scoring.star_rating(50, 1000), 1)

    def test_stars_never_exceed_five_or_drop_below_one(self):
        for score in range(0, 1400, 37):
            self.assertTrue(1 <= scoring.star_rating(score, 1000) <= 5)

    def test_rating_is_relative_to_the_case(self):
        # The same raw score means different things in a big and a small case.
        self.assertEqual(scoring.star_rating(400, 420), 5)
        self.assertEqual(scoring.star_rating(400, 1400), 1)


class TestXP(unittest.TestCase):
    def test_xp_scales_with_difficulty(self):
        easy = scoring.xp_earned(800, 1000, Difficulty.EASY, True)
        expert = scoring.xp_earned(800, 1000, Difficulty.EXPERT, True)
        self.assertGreater(expert, easy)

    def test_failure_earns_less_than_success(self):
        won = scoring.xp_earned(800, 1000, Difficulty.HARD, True)
        lost = scoring.xp_earned(800, 1000, Difficulty.HARD, False)
        self.assertGreater(won, lost)

    def test_failure_still_earns_something(self):
        self.assertGreater(scoring.xp_earned(0, 1000, Difficulty.EASY, False), 0)


class TestPar(unittest.TestCase):
    def setUp(self):
        self.cases = load_all()

    def test_every_case_has_a_positive_par(self):
        for case in self.cases:
            self.assertGreater(scoring.par_score(case), 0, case.title)

    def test_par_covers_all_evidence_at_minimum(self):
        for case in self.cases:
            floor = SCORE_TABLE["evidence_found"] * case.total_evidence
            self.assertGreaterEqual(scoring.par_score(case), floor, case.title)


if __name__ == "__main__":
    unittest.main()

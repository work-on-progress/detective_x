"""The machine learning model, and the guarantee that it generalises."""

import unittest

from detective_x.engine.analyst import (
    N_FEATURES,
    DeductionEngine,
    GaussianNaiveBayes,
    LogisticRegression,
    extract_features,
)
from detective_x.engine.deduction import find_contradictions
from detective_x.engine.loader import load_all


class TestFeatures(unittest.TestCase):
    def setUp(self):
        self.cases = load_all()

    def test_one_vector_per_suspect_of_the_right_length(self):
        for case in self.cases:
            full = {ev.id for ev in case.evidence}
            vectors = extract_features(case, full, find_contradictions(case, full))
            self.assertEqual(set(vectors), {s.id for s in case.suspects})
            for vec in vectors.values():
                self.assertEqual(len(vec), N_FEATURES)

    def test_features_are_normalised(self):
        for case in self.cases:
            full = {ev.id for ev in case.evidence}
            for vec in extract_features(case, full, set()).values():
                for value in vec:
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 1.0)

    def test_no_evidence_gives_a_near_empty_vector(self):
        case = self.cases[0]
        for sid, vec in extract_features(case, set(), set()).items():
            self.assertEqual(vec[1], 0.0)   # no weight of evidence
            self.assertEqual(vec[4], 0.0)   # no reliability to average


class TestClassifiers(unittest.TestCase):
    def test_naive_bayes_separates_a_trivial_problem(self):
        X = [[0.0] * N_FEATURES, [1.0] * N_FEATURES] * 8
        y = [0, 1] * 8
        nb = GaussianNaiveBayes().fit(X, y)
        self.assertGreater(nb.probability([1.0] * N_FEATURES), 0.9)
        self.assertLess(nb.probability([0.0] * N_FEATURES), 0.1)

    def test_untrained_naive_bayes_is_agnostic(self):
        self.assertEqual(GaussianNaiveBayes().probability([0.5] * N_FEATURES), 0.5)

    def test_logistic_regression_learns_and_stays_bounded(self):
        X = [[0.0] * N_FEATURES, [1.0] * N_FEATURES] * 8
        y = [0, 1] * 8
        lr = LogisticRegression(epochs=300).fit(X, y)
        high = lr.predict_one([1.0] * N_FEATURES)
        low = lr.predict_one([0.0] * N_FEATURES)
        self.assertGreater(high, low)
        for p in (high, low):
            self.assertTrue(0.0 <= p <= 1.0)

    def test_sigmoid_does_not_overflow_at_extremes(self):
        lr = LogisticRegression()
        self.assertAlmostEqual(lr._sigmoid(-800), 0.0, places=6)
        self.assertAlmostEqual(lr._sigmoid(800), 1.0, places=6)


class TestDeductionEngine(unittest.TestCase):
    def setUp(self):
        self.cases = load_all()
        self.engine = DeductionEngine(self.cases)

    def test_leave_one_out_accuracy_is_high(self):
        """Each case is scored by a model that never trained on it."""
        result = self.engine.accuracy()
        self.assertGreaterEqual(result["accuracy"], 0.8, result)

    def test_the_case_under_investigation_is_excluded_from_training(self):
        case = self.cases[0]
        full = {ev.id for ev in case.evidence}
        result = self.engine.assess(case, full, find_contradictions(case, full))
        self.assertEqual(result["trained_on"], len(self.cases) - 1)

    def test_confidences_are_probabilities_and_shares_sum_to_100(self):
        for case in self.cases:
            full = {ev.id for ev in case.evidence}
            result = self.engine.assess(case, full, find_contradictions(case, full))
            for row in result["ranking"]:
                self.assertTrue(0.0 <= row["confidence"] <= 1.0)
            self.assertAlmostEqual(sum(r["share"] for r in result["ranking"]), 100.0, delta=0.5)

    def test_ranking_is_ordered(self):
        case = self.cases[3]
        full = {ev.id for ev in case.evidence}
        rows = self.engine.assess(case, full, find_contradictions(case, full))["ranking"]
        confidences = [r["confidence"] for r in rows]
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_it_admits_when_it_has_too_little_to_work_with(self):
        case = self.cases[0]
        result = self.engine.assess(case, set(), set())
        self.assertEqual(result["certainty"], "Insufficient evidence")

    def test_certainty_grows_with_evidence(self):
        case = self.cases[0]
        full = {ev.id for ev in case.evidence}
        strong = self.engine.assess(case, full, find_contradictions(case, full))
        self.assertIn(strong["certainty"], {"Strong", "Moderate"})
        self.assertEqual(strong["coverage"], 100)


if __name__ == "__main__":
    unittest.main()

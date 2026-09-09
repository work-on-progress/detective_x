"""Contradiction detection must be data-driven, not hard-coded per case."""

import unittest

from detective_x.engine.deduction import (
    contradiction_detail,
    discovered_contradictions,
    find_contradictions,
)
from detective_x.engine.loader import load_all
from detective_x.models.case import Case
from detective_x.models.entities import Statement, Suspect

BASE = {
    "schema_version": 1, "case_id": 900, "title": "Fixture", "subtitle": "",
    "difficulty": "Medium", "culprit_id": "a", "briefing": "b", "solution": "s",
    "topics": {"where": "where they were"},
    "suspects": [], "locations": [], "evidence": [], "timeline": [], "hints": [],
}


def build(statements_by_suspect, evidence=None):
    raw = dict(BASE)
    raw["suspects"] = [
        {"id": sid, "name": sid.title(), "age": 40, "occupation": "x",
         "relation": "y", "motive": "z", "base_suspicion": 10, "belongings": [],
         "statements": sts}
        for sid, sts in statements_by_suspect.items()
    ]
    raw["evidence"] = evidence or []
    return Case.from_dict(raw)


def stmt(topic, claim, unlocked_by=None):
    d = {"topic": topic, "claim": claim, "question": "q?", "text": f"I was in the {claim}."}
    if unlocked_by:
        d["unlocked_by"] = unlocked_by
    return d


class TestFindContradictions(unittest.TestCase):
    def test_disagreement_produces_a_contradiction(self):
        case = build({
            "a": [stmt("where", "kitchen")],
            "b": [stmt("where", "garden")],
            "c": [stmt("where", "garden")],
        })
        found = find_contradictions(case, set())
        self.assertEqual(found, {"a:where"})

    def test_agreement_produces_none(self):
        case = build({
            "a": [stmt("where", "garden")],
            "b": [stmt("where", "garden")],
        })
        self.assertEqual(find_contradictions(case, set()), set())

    def test_locked_statement_is_excluded_until_its_clue_is_found(self):
        evidence = [{"id": "e1", "name": "Clue", "description": "",
                     "type": "PHYSICAL", "reliability": 90}]
        case = build({
            "a": [stmt("where", "kitchen", unlocked_by="e1")],
            "b": [stmt("where", "garden")],
            "c": [stmt("where", "garden")],
        }, evidence)
        self.assertEqual(find_contradictions(case, set()), set())
        self.assertEqual(find_contradictions(case, {"e1"}), {"a:where"})

    def test_single_suspect_cannot_contradict_anyone(self):
        case = build({"a": [stmt("where", "kitchen")]})
        self.assertEqual(find_contradictions(case, set()), set())

    def test_detection_is_not_hard_coded_to_any_suspect_id(self):
        case = build({
            "zebra": [stmt("where", "roof")],
            "b": [stmt("where", "cellar")],
            "c": [stmt("where", "cellar")],
        })
        self.assertEqual(find_contradictions(case, set()), {"zebra:where"})


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.case = build({
            "a": [stmt("where", "kitchen")],
            "b": [stmt("where", "garden")],
            "c": [stmt("where", "garden")],
        })

    def test_nothing_is_discovered_before_asking(self):
        self.assertEqual(discovered_contradictions(self.case, set(), set()), set())

    def test_one_side_alone_is_not_enough(self):
        self.assertEqual(
            discovered_contradictions(self.case, set(), {"a:where"}), set()
        )

    def test_both_sides_reveal_it(self):
        self.assertEqual(
            discovered_contradictions(self.case, set(), {"a:where", "b:where"}),
            {"a:where"},
        )

    def test_discovered_is_always_a_subset_of_latent(self):
        asked = {f"{s}:where" for s in ("a", "b", "c")}
        latent = find_contradictions(self.case, set())
        self.assertTrue(discovered_contradictions(self.case, set(), asked) <= latent)


class TestDetail(unittest.TestCase):
    def test_detail_names_both_sides(self):
        case = build({
            "a": [stmt("where", "kitchen")],
            "b": [stmt("where", "garden")],
            "c": [stmt("where", "garden")],
        })
        detail = contradiction_detail(case, "a:where")
        self.assertEqual(detail["suspect"], "A")
        self.assertEqual(len(detail["contradicted_by"]), 2)
        self.assertEqual(detail["topic"], "where they were")


class TestRealCases(unittest.TestCase):
    def test_every_case_has_at_least_one_contradiction(self):
        for case in load_all():
            full = {ev.id for ev in case.evidence}
            self.assertTrue(find_contradictions(case, full), case.title)


if __name__ == "__main__":
    unittest.main()

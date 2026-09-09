"""The investigation session.

This is the only stateful part of the engine. It exposes verbs the player can
perform and returns plain dictionaries describing what happened. It never
prints and never reads input, so the terminal front-end and the browser
front-end drive exactly the same object.
"""

from __future__ import annotations

import random

from ..config import STARTING_SCORE
from ..exceptions import InvalidChoice
from ..models.case import Case, InvestigationState
from ..models.enums import CaseStatus, Difficulty
from . import deduction, scoring
from .analyst import DeductionEngine

BRUSH_OFF = [
    "I have already told you everything I know.",
    "Why do you keep coming back to me?",
    "I do not remember anything else. I wish I did.",
    "Perhaps I saw something. I could not swear to it.",
    "Ask someone else for a change.",
]

AMBIENT = [
    "A witness recalls one more detail, then thinks better of it.",
    "Another frame of footage is recovered from the damaged sector.",
    "Someone rephrases part of their earlier statement.",
    "A door that was locked earlier is now open.",
    "The duty log is amended without explanation.",
]


class Investigation:
    def __init__(
        self,
        case: Case,
        difficulty: Difficulty | None = None,
        state: InvestigationState | None = None,
        analyst: DeductionEngine | None = None,
        seed: int | None = None,
        debug: bool = False,
    ) -> None:
        self.case = case
        self.debug = debug
        self.rng = random.Random(seed)
        self.analyst = analyst
        diff = difficulty or case.difficulty
        self.state = state or InvestigationState(
            case_id=case.id,
            difficulty=diff,
            score=STARTING_SCORE,
            hints_remaining=diff.hint_count,
        )
        if debug:
            self.state.found_evidence = {e.id for e in case.evidence}
            self.state.questions_asked = {
                f"{s.id}:{st.topic}" for s in case.suspects for st in s.statements
            }
        self._refresh()

    # -- derived state ---------------------------------------------------
    def _refresh(self) -> None:
        self.state.contradictions = deduction.discovered_contradictions(
            self.case, self.state.found_evidence, self.state.questions_asked
        )

    @property
    def suspicion(self) -> dict[str, int]:
        return deduction.compute_suspicion(
            self.case, self.state.found_evidence, self.state.contradictions
        )

    def dashboard(self) -> dict:
        st = self.state
        return {
            "case": self.case.header(),
            "score": st.score,
            "hints_remaining": st.hints_remaining,
            "evidence_found": len(st.found_evidence),
            "evidence_total": self.case.total_evidence,
            "locations_visited": len(st.visited_locations),
            "locations_total": len(self.case.locations),
            "contradictions": len(st.contradictions),
            "completion": scoring.completion(st, self.case),
            "par": scoring.par_score(self.case),
            "status": st.status.name,
            "shows_meter": st.difficulty.shows_suspicion_meter,
            "difficulty": st.difficulty.value,
        }

    # -- locations -------------------------------------------------------
    def locations(self) -> list[dict]:
        out = []
        for loc in self.case.locations:
            searched = sum(
                1 for s in loc.searchables if f"{loc.id}/{s.id}" in self.state.searched
            )
            out.append(
                {
                    **loc.to_dict(),
                    "visited": loc.id in self.state.visited_locations,
                    "searched": searched,
                    "searchable_count": len(loc.searchables),
                    "exhausted": searched == len(loc.searchables),
                }
            )
        return out

    def enter_location(self, location_id: str) -> dict:
        loc = self.case.location_by_id(location_id)
        first = loc.id not in self.state.visited_locations
        self.state.visited_locations.add(loc.id)
        if first:
            self.state.record(f"Entered {loc.name}.")
        return {
            **loc.to_dict(),
            "first_visit": first,
            "searchables": [
                {
                    "id": s.id,
                    "label": s.label,
                    "searched": f"{loc.id}/{s.id}" in self.state.searched,
                }
                for s in loc.searchables
            ],
        }

    def search(self, location_id: str, searchable_id: str) -> dict:
        loc = self.case.location_by_id(location_id)
        target = next((s for s in loc.searchables if s.id == searchable_id), None)
        if target is None:
            raise InvalidChoice(f"nothing called {searchable_id!r} in {loc.name}")

        key = f"{loc.id}/{target.id}"
        repeat = key in self.state.searched
        self.state.searched.add(key)
        self.state.visited_locations.add(loc.id)

        if repeat:
            self.state.score = scoring.apply(self.state.score, "repeat_search")
            return {
                "repeat": True,
                "flavour": target.flavour or "You have already been through this.",
                "found": [],
                "unlocked": [],
                "delta": -10,
            }

        before = self.state.score
        found = []
        for eid in target.yields:
            if eid in self.state.found_evidence:
                continue
            if not deduction.is_available(self.case, eid, self.state.found_evidence):
                continue
            found.append(self._collect(eid))

        unlocked = self._resolve_chains()
        self._refresh()
        return {
            "repeat": False,
            "flavour": target.flavour,
            "found": found,
            "unlocked": unlocked,
            "delta": self.state.score - before,
            "ambient": self.rng.choice(AMBIENT) if self.rng.random() < 0.18 else None,
        }

    def _collect(self, eid: str) -> dict:
        ev = self.case.evidence_by_id(eid)
        self.state.found_evidence.add(eid)
        key = ev.implicates == self.case.culprit_id and not ev.is_red_herring
        self.state.score = scoring.apply(
            self.state.score, "key_evidence_found" if key else "evidence_found"
        )
        self.state.note(f"Recovered: {ev.name}")
        self.state.record(f"Recovered {ev.name}.")
        if ev.cleared_by and ev.cleared_by in self.state.found_evidence:
            self.state.score = scoring.apply(self.state.score, "red_herring_cleared")
        return {
            **ev.to_dict(),
            "newly_revealed_timeline": [
                t.time for t in self.case.timeline if t.revealed_by == eid
            ],
        }

    def _resolve_chains(self) -> list[dict]:
        unlocked: list[dict] = []
        while True:
            fresh = deduction.newly_unlocked(self.case, self.state.found_evidence)
            if not fresh:
                break
            for eid in sorted(fresh):
                unlocked.append(self._collect(eid))
                self.state.score = scoring.apply(self.state.score, "chain_unlocked")
        return unlocked

    # -- suspects and questioning ----------------------------------------
    def suspects(self) -> list[dict]:
        susp = self.suspicion
        show = self.state.difficulty.shows_suspicion_meter
        rows = []
        for s in self.case.suspects:
            rows.append(
                {
                    **s.to_dict(),
                    "suspicion": susp.get(s.id, 0) if show else None,
                    "questions_available": len(
                        s.available_statements(self.state.found_evidence)
                    ),
                    "questions_asked": sum(
                        1
                        for st in s.statements
                        if f"{s.id}:{st.topic}" in self.state.questions_asked
                    ),
                }
            )
        return rows

    def questions_for(self, suspect_id: str) -> list[dict]:
        s = self.case.suspect_by_id(suspect_id)
        out = []
        for st in s.available_statements(self.state.found_evidence):
            key = f"{s.id}:{st.topic}"
            out.append(
                {
                    "topic": st.topic,
                    "question": st.question,
                    "asked": key in self.state.questions_asked,
                    "unlocked": st.unlocked_by is not None,
                }
            )
        return out

    def ask(self, suspect_id: str, topic: str) -> dict:
        s = self.case.suspect_by_id(suspect_id)
        st = s.statement_on(topic)
        if st is None:
            raise InvalidChoice(f"{s.name} has nothing to say on {topic!r}")
        if st.unlocked_by and st.unlocked_by not in self.state.found_evidence:
            raise InvalidChoice("You have no grounds to ask that yet.")

        key = f"{s.id}:{topic}"
        repeat = key in self.state.questions_asked
        self.state.questions_asked.add(key)

        if repeat:
            self.state.score = scoring.apply(self.state.score, "repeat_question")
            return {
                "suspect": s.name,
                "answer": self.rng.choice(BRUSH_OFF),
                "repeat": True,
                "new_contradictions": [],
            }

        before = set(self.state.contradictions)
        self._refresh()
        fresh = self.state.contradictions - before
        details = []
        for cid in sorted(fresh):
            self.state.score = scoring.apply(self.state.score, "contradiction_found")
            detail = deduction.contradiction_detail(self.case, cid)
            self.state.note(f"Contradiction: {detail['suspect']} on {detail['topic']}")
            details.append(detail)

        self.state.note(f"{s.name} on {self.case.topics.get(topic, topic)}: {st.text}")
        return {
            "suspect": s.name,
            "suspect_id": s.id,
            "topic": self.case.topics.get(topic, topic),
            "answer": st.text,
            "repeat": False,
            "new_contradictions": details,
        }

    # -- evidence --------------------------------------------------------
    def evidence_held(self) -> list[dict]:
        rows = []
        for ev in self.case.evidence:
            if ev.id not in self.state.found_evidence:
                continue
            cleared = ev.is_red_herring and ev.cleared_by in self.state.found_evidence
            rows.append({**ev.to_dict(), "cleared": cleared})
        return rows

    def comparable_evidence(self) -> list[dict]:
        return [e for e in self.evidence_held() if e["comparable"]]

    def comparison_targets(self, evidence_id: str) -> list[str]:
        ev = self.case.evidence_by_id(evidence_id)
        if not ev.comparable:
            raise InvalidChoice("That clue cannot be matched against anything.")
        return sorted({b for s in self.case.suspects for b in s.belongings})

    def compare(self, evidence_id: str, target: str) -> dict:
        if evidence_id not in self.state.found_evidence:
            raise InvalidChoice("You do not hold that clue.")
        key = f"{evidence_id}|{target}"
        if key in self.state.comparisons:
            return {**deduction.compare(self.case, evidence_id, target), "repeat": True}

        self.state.comparisons.add(key)
        result = deduction.compare(self.case, evidence_id, target)
        self.state.score = scoring.apply(
            self.state.score,
            "correct_comparison" if result["match"] else "wrong_comparison",
        )
        if result["match"]:
            self.state.note(f"{result['evidence']} matches {target}.")
        return {**result, "repeat": False}

    def timeline(self) -> list[dict]:
        return [
            {"time": t.time, "text": t.text, "revealed": t.hidden}
            for t in self.case.timeline
            if t.is_visible(self.state.found_evidence)
        ]

    def board(self) -> list[dict]:
        return deduction.evidence_board(
            self.case, self.state.found_evidence, self.state.contradictions
        )

    def reliability(self) -> list[dict]:
        return deduction.reliability_bands(self.case, self.state.found_evidence)

    def notebook(self) -> dict:
        open_threads = [
            f"Where is {ev.name.lower()}?"
            for ev in self.case.evidence
            if ev.id not in self.state.found_evidence and not ev.requires
        ][:4]
        return {"confirmed": self.state.notebook[-14:], "open": open_threads}

    # -- assistance ------------------------------------------------------
    def hint(self) -> dict:
        if self.state.hints_remaining <= 0:
            return {"available": False, "text": "No further assistance available."}
        remaining = [h for h in self.case.hints if h not in self.state.hints_shown]
        if not remaining:
            return {"available": False, "text": "The department has nothing more."}
        text = remaining[0]
        self.state.hints_shown.append(text)
        self.state.hints_remaining -= 1
        self.state.score = scoring.apply(self.state.score, "hint_used")
        return {
            "available": True,
            "text": text,
            "penalty": 50,
            "remaining": self.state.hints_remaining,
        }

    def assess(self) -> dict:
        if self.analyst is None:
            return {"available": False}
        result = self.analyst.assess(
            self.case, self.state.found_evidence, self.state.contradictions
        )
        return {"available": True, **result}

    # -- resolution ------------------------------------------------------
    def accuse(self, suspect_id: str) -> dict:
        suspect = self.case.suspect_by_id(suspect_id)
        solved = suspect_id == self.case.culprit_id
        self.state.accused = suspect_id
        self.state.status = CaseStatus.SOLVED if solved else CaseStatus.FAILED
        summary = scoring.summarise(self.state, self.case, solved)
        self.state.score = summary["score"]
        return {
            **summary,
            "accused_id": suspect_id,
            "accused": suspect.name,
            "solution": self.case.solution,
            "missed": [] if solved else scoring.missed_evidence(self.state, self.case),
        }

    def snapshot(self) -> dict:
        return self.state.to_dict()

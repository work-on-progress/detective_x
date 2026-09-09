"""The case object and the mutable player-side state."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..exceptions import CaseDataError
from .entities import Evidence, Location, Statement, Suspect, TimelineEvent
from .enums import CaseStatus, Difficulty, Rank

SCHEMA_VERSION = 1


@dataclass
class Case:
    id: int
    title: str
    subtitle: str
    difficulty: Difficulty
    culprit_id: str
    setting: str
    crime: str
    window: str
    briefing: str
    solution: str
    suspects: list[Suspect]
    locations: list[Location]
    evidence: list[Evidence]
    timeline: list[TimelineEvent]
    hints: list[str]
    topics: dict[str, str] = field(default_factory=dict)

    # -- lookups ---------------------------------------------------------
    def evidence_by_id(self, eid: str) -> Evidence:
        for ev in self.evidence:
            if ev.id == eid:
                return ev
        raise CaseDataError(f"case {self.id}: no evidence with id {eid!r}")

    def suspect_by_id(self, sid: str) -> Suspect:
        for sus in self.suspects:
            if sus.id == sid:
                return sus
        raise CaseDataError(f"case {self.id}: no suspect with id {sid!r}")

    def location_by_id(self, lid: str) -> Location:
        for loc in self.locations:
            if loc.id == lid:
                return loc
        raise CaseDataError(f"case {self.id}: no location with id {lid!r}")

    @property
    def culprit(self) -> Suspect:
        return self.suspect_by_id(self.culprit_id)

    @property
    def total_evidence(self) -> int:
        return len(self.evidence)

    # -- construction ----------------------------------------------------
    @classmethod
    def from_dict(cls, raw: dict) -> "Case":
        try:
            case = cls(
                id=int(raw["case_id"]),
                title=raw["title"],
                subtitle=raw.get("subtitle", ""),
                difficulty=Difficulty.parse(raw["difficulty"]),
                culprit_id=raw["culprit_id"],
                setting=raw.get("setting", ""),
                crime=raw.get("crime", ""),
                window=raw.get("window", ""),
                briefing=raw["briefing"],
                solution=raw["solution"],
                suspects=[Suspect.from_dict(s) for s in raw["suspects"]],
                locations=[Location.from_dict(l) for l in raw["locations"]],
                evidence=[Evidence.from_dict(e) for e in raw["evidence"]],
                timeline=[TimelineEvent.from_dict(t) for t in raw.get("timeline", [])],
                hints=list(raw.get("hints", [])),
                topics=dict(raw.get("topics", {})),
            )
        except KeyError as exc:
            raise CaseDataError(f"case file missing required field: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise CaseDataError(f"case file has an invalid value: {exc}") from exc
        return case

    def header(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "difficulty": self.difficulty.value,
            "setting": self.setting,
            "crime": self.crime,
            "window": self.window,
            "suspects": len(self.suspects),
            "evidence": len(self.evidence),
            "unlock_xp": self.difficulty.unlock_xp,
        }


@dataclass
class Detective:
    name: str
    xp: int = 0
    cases_won: int = 0
    cases_lost: int = 0
    best_score: int = 0
    completed: set[int] = field(default_factory=set)
    failed: set[int] = field(default_factory=set)

    @property
    def rank(self) -> Rank:
        return Rank.from_xp(self.xp)

    @property
    def stars(self) -> int:
        total = self.cases_won + self.cases_lost
        if total == 0:
            return 0
        return round(5 * self.cases_won / total)

    @property
    def rank_progress(self) -> tuple[int, int]:
        """Returns (xp_into_current_rank, xp_span_of_current_rank)."""
        current = self.rank
        nxt = current.next_rank
        if nxt is None:
            return (1, 1)
        return (self.xp - current.value, nxt.value - current.value)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "xp": self.xp,
            "cases_won": self.cases_won,
            "cases_lost": self.cases_lost,
            "best_score": self.best_score,
            "completed": sorted(self.completed),
            "failed": sorted(self.failed),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Detective":
        return cls(
            name=raw.get("name", "Detective"),
            xp=int(raw.get("xp", 0)),
            cases_won=int(raw.get("cases_won", 0)),
            cases_lost=int(raw.get("cases_lost", 0)),
            best_score=int(raw.get("best_score", 0)),
            completed=set(raw.get("completed", [])),
            failed=set(raw.get("failed", [])),
        )


@dataclass
class InvestigationState:
    """Everything that changes during one case. This is what gets saved."""

    case_id: int
    difficulty: Difficulty
    score: int = 1000
    hints_remaining: int = 3
    hints_shown: list[str] = field(default_factory=list)
    found_evidence: set[str] = field(default_factory=set)
    visited_locations: set[str] = field(default_factory=set)
    searched: set[str] = field(default_factory=set)
    questions_asked: set[str] = field(default_factory=set)
    contradictions: set[str] = field(default_factory=set)
    comparisons: set[str] = field(default_factory=set)
    notebook: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    status: CaseStatus = CaseStatus.IN_PROGRESS
    accused: str | None = None

    def note(self, line: str) -> None:
        if line not in self.notebook:
            self.notebook.append(line)

    def record(self, line: str) -> None:
        self.log.append(line)
        del self.log[:-40]

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "difficulty": self.difficulty.value,
            "score": self.score,
            "hints_remaining": self.hints_remaining,
            "hints_shown": self.hints_shown,
            "found_evidence": sorted(self.found_evidence),
            "visited_locations": sorted(self.visited_locations),
            "searched": sorted(self.searched),
            "questions_asked": sorted(self.questions_asked),
            "contradictions": sorted(self.contradictions),
            "comparisons": sorted(self.comparisons),
            "notebook": self.notebook,
            "log": self.log,
            "status": self.status.name,
            "accused": self.accused,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "InvestigationState":
        return cls(
            case_id=int(raw["case_id"]),
            difficulty=Difficulty.parse(raw["difficulty"]),
            score=int(raw.get("score", 1000)),
            hints_remaining=int(raw.get("hints_remaining", 3)),
            hints_shown=list(raw.get("hints_shown", [])),
            found_evidence=set(raw.get("found_evidence", [])),
            visited_locations=set(raw.get("visited_locations", [])),
            searched=set(raw.get("searched", [])),
            questions_asked=set(raw.get("questions_asked", [])),
            contradictions=set(raw.get("contradictions", [])),
            comparisons=set(raw.get("comparisons", [])),
            notebook=list(raw.get("notebook", [])),
            log=list(raw.get("log", [])),
            status=CaseStatus[raw.get("status", "IN_PROGRESS")],
            accused=raw.get("accused"),
        )

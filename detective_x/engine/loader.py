"""Reads case files from disk and refuses to accept broken ones."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import CASE_DIR
from ..exceptions import CaseDataError
from ..models.case import Case
from ..models.enums import EvidenceType


def validate(case: Case) -> None:
    """The nine structural rules. Raises CaseDataError on the first failure."""
    suspect_ids = {s.id for s in case.suspects}
    evidence_ids = {e.id for e in case.evidence}
    where = f"case {case.id} ({case.title})"

    if case.culprit_id not in suspect_ids:
        raise CaseDataError(f"{where}: culprit {case.culprit_id!r} is not a suspect")

    for ev in case.evidence:
        if ev.implicates and ev.implicates not in suspect_ids:
            raise CaseDataError(
                f"{where}: evidence {ev.id!r} implicates unknown suspect {ev.implicates!r}"
            )
        for dep in ev.requires:
            if dep not in evidence_ids:
                raise CaseDataError(
                    f"{where}: evidence {ev.id!r} requires unknown clue {dep!r}"
                )
        for dep in ev.unlocks:
            if dep not in evidence_ids:
                raise CaseDataError(
                    f"{where}: evidence {ev.id!r} unlocks unknown clue {dep!r}"
                )
        if ev.cleared_by and ev.cleared_by not in evidence_ids:
            raise CaseDataError(
                f"{where}: evidence {ev.id!r} cleared by unknown clue {ev.cleared_by!r}"
            )
        if not isinstance(ev.type, EvidenceType):
            raise CaseDataError(f"{where}: evidence {ev.id!r} has an invalid type")
        if not 0 <= ev.reliability <= 100:
            raise CaseDataError(f"{where}: evidence {ev.id!r} reliability out of range")

    for loc in case.locations:
        for sr in loc.searchables:
            for eid in sr.yields:
                if eid not in evidence_ids:
                    raise CaseDataError(
                        f"{where}: {loc.id}/{sr.id} yields unknown clue {eid!r}"
                    )

    for te in case.timeline:
        if te.revealed_by and te.revealed_by not in evidence_ids:
            raise CaseDataError(
                f"{where}: timeline entry {te.time!r} revealed by unknown clue"
            )

    incriminating = [
        ev
        for ev in case.evidence
        if ev.implicates == case.culprit_id and not ev.is_red_herring
    ]
    if not incriminating:
        raise CaseDataError(f"{where}: no clue implicates the culprit — unsolvable")

    reachable = {
        eid
        for loc in case.locations
        for sr in loc.searchables
        for eid in sr.yields
    }
    chained = {e.id for e in case.evidence if e.requires}
    orphans = evidence_ids - reachable - chained
    if orphans:
        raise CaseDataError(
            f"{where}: clues can never be found: {sorted(orphans)}"
        )


def load_case_file(path: Path) -> Case:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CaseDataError(f"case file not found: {path}") from exc
    except OSError as exc:
        raise CaseDataError(f"case file unreadable: {path} ({exc})") from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CaseDataError(f"{path.name}: malformed JSON at line {exc.lineno}") from exc

    case = Case.from_dict(raw)
    validate(case)
    return case


def load_case_dict(raw: dict) -> Case:
    """Used by the browser build, which fetches JSON rather than reading files."""
    case = Case.from_dict(raw)
    validate(case)
    return case


def load_all(directory: Path | None = None) -> list[Case]:
    """Load every case file, skipping (but reporting) any that fail."""
    directory = directory or CASE_DIR
    if not directory.is_dir():
        raise CaseDataError(f"case directory missing: {directory}")

    cases: list[Case] = []
    problems: list[str] = []
    for path in sorted(directory.glob("case_*.json")):
        try:
            cases.append(load_case_file(path))
        except CaseDataError as exc:
            problems.append(str(exc))

    if not cases:
        detail = "; ".join(problems) if problems else "directory is empty"
        raise CaseDataError(f"no playable cases found: {detail}")

    cases.sort(key=lambda c: c.id)
    return cases

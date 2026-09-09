"""Pure scoring arithmetic. No printing, no input, nothing outside changed."""

from __future__ import annotations

from ..config import BASE_XP_FAILED, BASE_XP_SOLVED, SCORE_TABLE, STAR_THRESHOLDS
from ..exceptions import UnknownScoreAction
from ..models.case import Case, InvestigationState
from ..models.enums import Difficulty


def apply(score: int, action: str, times: int = 1) -> int:
    """Return the new score after applying `action` `times` over. Never negative."""
    if action not in SCORE_TABLE:
        raise UnknownScoreAction(f"no such scoring action: {action!r}")
    return max(0, score + SCORE_TABLE[action] * times)


def par_score(case: Case) -> int:
    """The most a flawless investigation of this case could earn.

    Cases differ in size, so a fixed star threshold would reward long cases and
    punish short ones. Every rating is measured against this instead.
    """
    from .deduction import find_contradictions

    total = 0
    full = {ev.id for ev in case.evidence}
    for ev in case.evidence:
        key = ev.implicates == case.culprit_id and not ev.is_red_herring
        total += SCORE_TABLE["key_evidence_found" if key else "evidence_found"]
        if ev.requires:
            total += SCORE_TABLE["chain_unlocked"]
        if ev.cleared_by:
            total += SCORE_TABLE["red_herring_cleared"]
        total += SCORE_TABLE["correct_comparison"] * len(ev.matches)
    total += SCORE_TABLE["contradiction_found"] * len(find_contradictions(case, full))
    return max(1, total)


def star_rating(score: int, par: int) -> int:
    ratio = score / par if par else 0.0
    for threshold, stars in STAR_THRESHOLDS:
        if ratio >= threshold:
            return stars
    return 1


def xp_earned(score: int, par: int, difficulty: Difficulty, solved: bool) -> int:
    if not solved:
        return round(BASE_XP_FAILED * difficulty.xp_multiplier)
    ratio = min(1.0, score / par) if par else 0.0
    return round(BASE_XP_SOLVED * (0.5 + ratio) * difficulty.xp_multiplier)


def completion(state: InvestigationState, case: Case) -> int:
    """Investigation progress as a percentage, blending several signals."""
    if case.total_evidence == 0:
        return 0
    ev = len(state.found_evidence) / case.total_evidence
    loc = len(state.visited_locations) / max(1, len(case.locations))
    talk = min(1.0, len(state.questions_asked) / max(1, len(case.suspects) * 3))
    return round(100 * (0.55 * ev + 0.2 * loc + 0.25 * talk))


def summarise(state: InvestigationState, case: Case, solved: bool) -> dict:
    """Build the end-of-case figures. Pure — returns data, displays nothing."""
    par = par_score(case)
    final = state.score if solved else apply(state.score, "wrong_accusation")
    return {
        "solved": solved,
        "score": final,
        "par": par,
        "percent": round(100 * min(1.0, final / par)) if par else 0,
        "stars": star_rating(final, par),
        "xp": xp_earned(final, par, case.difficulty, solved),
        "evidence_found": len(state.found_evidence),
        "evidence_total": case.total_evidence,
        "contradictions": len(state.contradictions),
        "hints_used": len(state.hints_shown),
        "culprit": case.culprit.name,
        "accused": case.suspect_by_id(state.accused).name if state.accused else None,
    }


def missed_evidence(state: InvestigationState, case: Case) -> list[str]:
    """Key clues the player never found, for the failure screen."""
    return [
        ev.name
        for ev in case.evidence
        if ev.id not in state.found_evidence
        and ev.implicates == case.culprit_id
        and not ev.is_red_herring
    ]

"""Contradiction detection, suspicion scoring, and evidence chaining.

Every function here is pure: same inputs, same outputs, nothing displayed and
nothing outside the function changed. This is the part of the game that gets
unit tested.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ..config import CONTRADICTION_PENALTY
from ..models.case import Case
from ..models.entities import Evidence


# --------------------------------------------------------------------------
# Contradictions
# --------------------------------------------------------------------------
def find_contradictions(case: Case, found: set[str]) -> set[str]:
    """Contradictions visible with the evidence currently held.

    A contradiction is recorded when two suspects give different claims on the
    same topic key. Statements gated behind unfound evidence are excluded, so
    finding that evidence makes new contradictions surface on its own.

    Returns ids shaped "suspect_id:topic".
    """
    claims: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for suspect in case.suspects:
        for st in suspect.available_statements(found):
            claims[st.topic].add((suspect.id, st.claim))

    contradictions: set[str] = set()
    for topic, entries in claims.items():
        distinct = {claim for _, claim in entries}
        if len(distinct) > 1:
            majority = Counter(claim for _, claim in entries).most_common(1)[0][0]
            for sid, claim in entries:
                if claim != majority:
                    contradictions.add(f"{sid}:{topic}")

    return contradictions


def contradiction_detail(case: Case, contradiction_id: str) -> dict:
    """Expand a contradiction id into the two conflicting statements."""
    sid, topic = contradiction_id.split(":", 1)
    liar = case.suspect_by_id(sid)
    own = liar.statement_on(topic)
    others = [
        (s, s.statement_on(topic))
        for s in case.suspects
        if s.id != sid and s.statement_on(topic) is not None
    ]
    against = [
        {"name": s.name, "text": st.text}
        for s, st in others
        if st is not None and own is not None and st.claim != own.claim
    ]
    return {
        "id": contradiction_id,
        "topic": case.topics.get(topic, topic.replace("_", " ")),
        "suspect": liar.name,
        "suspect_id": liar.id,
        "claim": own.text if own else "",
        "contradicted_by": against,
        "penalty": CONTRADICTION_PENALTY,
    }


# --------------------------------------------------------------------------
# Suspicion
# --------------------------------------------------------------------------
def _is_active(ev: Evidence, found: set[str]) -> bool:
    """A red herring stops counting once the clue that clears it is found."""
    if not ev.is_red_herring:
        return True
    return not (ev.cleared_by and ev.cleared_by in found)


def raw_suspicion(
    case: Case,
    found: set[str],
    contradictions: set[str],
) -> dict[str, int]:
    """Unclamped suspicion totals. Reliability scales every contribution.

    Kept separate from the displayed figure because clamping at 100 creates
    ties between suspects whose totals differ, which would make a case look
    ambiguous when it is not.
    """
    scores: dict[str, int] = defaultdict(int)
    for suspect in case.suspects:
        scores[suspect.id] = suspect.base_suspicion

    for eid in found:
        try:
            ev = case.evidence_by_id(eid)
        except Exception:
            continue
        if ev.implicates and _is_active(ev, found):
            scores[ev.implicates] += ev.effective_weight

    for cid in contradictions:
        sid = cid.split(":", 1)[0]
        scores[sid] += CONTRADICTION_PENALTY

    return dict(scores)


def compute_suspicion(
    case: Case,
    found: set[str],
    contradictions: set[str],
) -> dict[str, int]:
    """Suspicion as a 0-100 meter for display."""
    return {sid: max(0, min(100, v))
            for sid, v in raw_suspicion(case, found, contradictions).items()}


def leading_suspect(suspicion: dict[str, int]) -> str | None:
    if not suspicion:
        return None
    top = max(suspicion.values())
    leaders = [sid for sid, v in suspicion.items() if v == top]
    return leaders[0] if len(leaders) == 1 else None


# --------------------------------------------------------------------------
# Evidence chains
# --------------------------------------------------------------------------
def newly_unlocked(case: Case, found: set[str]) -> set[str]:
    """Evidence whose prerequisites are now all satisfied."""
    return {
        ev.id
        for ev in case.evidence
        if ev.id not in found and ev.requires and set(ev.requires) <= found
    }


def is_available(case: Case, evidence_id: str, found: set[str]) -> bool:
    ev = case.evidence_by_id(evidence_id)
    return not ev.requires or set(ev.requires) <= found


def compare(case: Case, evidence_id: str, target: str) -> dict:
    """Compare a clue against a suspect's belonging. Pure lookup, no scoring."""
    ev = case.evidence_by_id(evidence_id)
    hit = target in ev.matches
    confidence = ev.reliability if hit else max(4, 100 - ev.reliability - 30)
    if hit:
        verdict = "STRONG MATCH" if ev.reliability >= 85 else "PROBABLE MATCH"
    else:
        verdict = "NO MATCH"
    return {
        "evidence": ev.name,
        "target": target,
        "match": hit,
        "verdict": verdict,
        "confidence": confidence,
        "implicates": ev.implicates if hit else None,
    }


def reliability_bands(case: Case, found: set[str]) -> list[dict]:
    """Held evidence ordered by how much it can be trusted."""
    held = [ev for ev in case.evidence if ev.id in found]
    held.sort(key=lambda e: (-e.reliability, e.name))
    return [
        {
            "id": ev.id,
            "name": ev.name,
            "type": ev.type.value,
            "reliability": ev.reliability,
            "confirmed": ev.is_confirmed,
        }
        for ev in held
    ]


def evidence_board(case: Case, found: set[str], contradictions: set[str]) -> list[dict]:
    """Suspect-centred view of what currently points where."""
    by_suspect: dict[str, list[dict]] = defaultdict(list)

    for eid in sorted(found):
        try:
            ev = case.evidence_by_id(eid)
        except Exception:
            continue
        if not ev.implicates:
            continue
        cleared = not _is_active(ev, found)
        by_suspect[ev.implicates].append(
            {
                "label": ev.name,
                "kind": "evidence",
                "weight": 0 if cleared else ev.effective_weight,
                "cleared": cleared,
            }
        )

    for cid in sorted(contradictions):
        sid, topic = cid.split(":", 1)
        by_suspect[sid].append(
            {
                "label": f"False account: {case.topics.get(topic, topic)}",
                "kind": "contradiction",
                "weight": CONTRADICTION_PENALTY,
                "cleared": False,
            }
        )

    board = []
    for suspect in case.suspects:
        threads = by_suspect.get(suspect.id, [])
        if threads:
            board.append(
                {
                    "suspect": suspect.name,
                    "suspect_id": suspect.id,
                    "threads": sorted(threads, key=lambda t: -t["weight"]),
                }
            )
    return sorted(board, key=lambda b: -sum(t["weight"] for t in b["threads"]))


def discovered_contradictions(
    case: Case,
    found: set[str],
    asked: set[str],
) -> set[str]:
    """Latent contradictions the player has actually uncovered.

    A contradiction only counts once the player has heard both sides: the
    false account, and at least one statement that conflicts with it. Without
    this filter the whole set would exist from the first second of the case and
    the player would never earn any of it.
    """
    latent = find_contradictions(case, found)
    out: set[str] = set()
    for cid in latent:
        sid, topic = cid.split(":", 1)
        if f"{sid}:{topic}" not in asked:
            continue
        liar = case.suspect_by_id(sid)
        own = liar.statement_on(topic)
        if own is None:
            continue
        heard_conflict = any(
            f"{other.id}:{topic}" in asked
            and (st := other.statement_on(topic)) is not None
            and st.claim != own.claim
            for other in case.suspects
            if other.id != sid
        )
        if heard_conflict:
            out.add(cid)
    return out

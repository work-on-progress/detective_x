"""Pre-flight check: prove every shipped case is playable and winnable.

Run in CI before anything is published. It plays all fifteen cases through
the real engine and refuses to pass if any of them cannot be solved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detective_x.engine.analyst import DeductionEngine
from detective_x.engine.deduction import find_contradictions, raw_suspicion
from detective_x.engine.investigation import Investigation
from detective_x.engine.loader import load_all


def main() -> int:
    cases = load_all()
    analyst = DeductionEngine(cases)
    failures: list[str] = []

    print(f"{'#':>3}  {'case':32} {'score':>10}  {'stars':>5}  {'margin':>6}  model")
    print("-" * 74)

    for case in cases:
        inv = Investigation(case, analyst=analyst, seed=11)
        for loc in case.locations:
            for searchable in loc.searchables:
                inv.search(loc.id, searchable.id)
        for suspect in case.suspects:
            for st in suspect.available_statements(inv.state.found_evidence):
                inv.ask(suspect.id, st.topic)

        full = {ev.id for ev in case.evidence}
        scores = raw_suspicion(case, full, find_contradictions(case, full))
        ordered = sorted(scores.items(), key=lambda kv: -kv[1])
        margin = ordered[0][1] - ordered[1][1]

        assessment = inv.assess()
        model_pick = assessment["ranking"][0]["suspect_id"]
        result = inv.accuse(case.culprit_id)

        if len(inv.state.found_evidence) != case.total_evidence:
            failures.append(f"{case.title}: not every clue is reachable")
        if ordered[0][0] != case.culprit_id:
            failures.append(f"{case.title}: evidence does not point at the culprit")
        if margin < 25:
            failures.append(f"{case.title}: the culprit only leads by {margin}")
        if result["stars"] < 3:
            failures.append(f"{case.title}: a thorough player only earns {result['stars']} stars")

        print(
            f"{case.id:>3}  {case.title[:32]:32} "
            f"{result['score']:>4}/{result['par']:<5} {result['stars']:>5}  "
            f"{margin:>6}  {'hit' if model_pick == case.culprit_id else 'MISS'}"
        )

    accuracy = analyst.accuracy()
    print("-" * 74)
    print(f"deduction engine, leave-one-case-out: "
          f"{accuracy['correct']}/{accuracy['total']} ({accuracy['accuracy']:.0%})")

    if accuracy["accuracy"] < 0.8:
        failures.append(f"the model only reaches {accuracy['accuracy']:.0%} accuracy")

    if failures:
        print("\nFAILED")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("\nAll cases verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

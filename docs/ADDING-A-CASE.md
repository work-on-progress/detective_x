# Adding a case

The engine loads any valid case file without a code change. If you find
yourself editing `engine/` to make a new case work, the case is fighting the
design — change the case, not the engine.

## 1. Write it in Python

Add a `case(...)` block to `tools/cases_c.py` (or a new `cases_d.py`, imported
from `tools/build_cases.py`). The helpers in `tools/casekit.py` keep it
readable.

```python
CASES.append(case(
    16, "Title", "One-line subtitle",
    "Medium",              # Easy | Medium | Hard | Expert
    "culprit_id",
    "Setting", "Offence", "Time window",
    "The briefing the player reads before starting.",
    "What actually happened, revealed at the end.",
    {"topic_key": "how the topic is described in the interface"},
    [ ...suspects... ], [ ...locations... ],
    [ ...evidence... ], [ ...timeline... ], [ ...hints... ],
))
```

## 2. The rules a case must satisfy

The loader rejects a case that breaks any of these, so a broken case can never
reach a player:

1. The culprit is one of the suspects.
2. Every `implicates` value names a real suspect.
3. Every `requires` and `unlocks` value names a real clue.
4. Every searchable's `yields` names a real clue.
5. Every timeline `revealed_by` names a real clue.
6. The difficulty matches a defined level.
7. Every evidence type matches a defined type.
8. Every reliability is between 0 and 100.
9. At least one clue that is not a red herring implicates the culprit.
10. Every clue is either yielded by a searchable or unlocked by a chain.

`tools/verify.py` adds four more, checked in CI:

- Every clue is actually reachable in play.
- With all evidence found, the culprit has the highest suspicion.
- The culprit leads the runner-up by at least 25 points.
- A thorough player earns at least three stars.

## 3. Design guidance

**Contradictions need three suspects on a topic, not two.** Detection takes the
majority claim as true and flags the minority. With two suspects disagreeing
there is no majority, so give at least three people a statement on any topic
you want to produce a contradiction.

**A red herring must never implicate the culprit.** Give each one a `cleared_by`
pointing at the clue that neutralises it. A test enforces both.

**Chain at most two or three clues deep.** Longer chains mean a player who
misses one search is stuck with no idea why.

**Trace evidence gets `matches`.** Only clues with a `matches` list can be
compared against belongings, so a player is never invited to guess through a
list of things that cannot match.

## 4. Build and check

```bash
python tools/build_cases.py
python tools/build_manifest.py
python -m unittest discover -s tests -t .
python tools/verify.py
python -m detective_x --case 16 --debug
```

Commit the regenerated JSON along with your Python source — CI checks that the
two are in step.

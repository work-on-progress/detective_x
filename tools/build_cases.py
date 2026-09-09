"""Emit the case JSON files from the readable Python definitions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cases_a, cases_b, cases_c
from casekit import write

OUT = Path(__file__).resolve().parent.parent / "detective_x" / "data" / "cases"

def main() -> int:
    cases = cases_a.CASES + cases_b.CASES + cases_c.CASES
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"duplicate case ids: {ids}")
    n = write(cases, OUT)
    print(f"wrote {n} cases to {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

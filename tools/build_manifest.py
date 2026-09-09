"""List every file the browser build needs to fetch."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main() -> int:
    py = sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in (ROOT / "detective_x").rglob("*.py")
    )
    cases = sorted(p.name for p in (ROOT / "detective_x/data/cases").glob("case_*.json"))
    manifest = {"python": py, "cases": cases}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {len(py)} modules, {len(cases)} cases")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

"""The browser front-end and the Python engine must agree on their contract.

The two halves are written in different languages and cannot be type-checked
against each other, so this test reads the JavaScript, extracts every engine
call it makes, and checks that each one exists and behaves.
"""

import glob
import json
import re
import unittest
from pathlib import Path

from detective_x.ui.web import SESSION, Session, api

ROOT = Path(__file__).parent.parent
APP_JS = ROOT / "assets" / "js" / "app.js"
BRIDGE_JS = ROOT / "assets" / "js" / "bridge.js"
CALL = re.compile(r'Bridge\.call\(\s*"([a-z_]+)"')


def load_everything():
    files = sorted(glob.glob(str(ROOT / "detective_x/data/cases/case_*.json")))
    payload = json.dumps([json.loads(Path(f).read_text(encoding="utf-8")) for f in files])
    return json.loads(api("load_cases", json.dumps({"payload": payload})))


class TestContract(unittest.TestCase):
    def test_every_method_the_interface_calls_exists(self):
        source = APP_JS.read_text(encoding="utf-8") + BRIDGE_JS.read_text(encoding="utf-8")
        called = set(CALL.findall(source))
        self.assertGreater(len(called), 12, "the regex should find the interface's calls")
        for method in sorted(called):
            self.assertTrue(
                hasattr(Session, method),
                f"the interface calls Bridge.call('{method}') but Session has no such method",
            )

    def test_an_unknown_method_is_refused_rather_than_crashing(self):
        result = json.loads(api("definitely_not_a_method"))
        self.assertFalse(result["ok"])

    def test_private_attributes_cannot_be_reached(self):
        result = json.loads(api("_case", json.dumps({"case_id": 1})))
        self.assertFalse(result["ok"])

    def test_a_malformed_payload_is_refused_rather_than_crashing(self):
        result = json.loads(api("library", "{not json"))
        self.assertFalse(result["ok"])
        self.assertIn("bad payload", result["error"])

    def test_calling_a_case_method_with_no_case_open_fails_cleanly(self):
        fresh = Session()
        self.assertFalse(fresh.dashboard()["ok"])
        self.assertFalse(fresh.locations()["ok"])
        self.assertFalse(fresh.accuse(suspect_id="anyone")["ok"])

    def test_every_response_is_json_serialisable(self):
        """Anything that cannot cross into JavaScript is a bug."""
        load_everything()
        SESSION.detective.xp = 99999
        case = SESSION.cases[0]
        self.assertTrue(json.loads(api("start", json.dumps({"case_id": case.id})))["ok"])

        checks = [
            ("library", {}),
            ("profile", {}),
            ("dashboard", {}),
            ("locations", {}),
            ("enter", {"location_id": case.locations[0].id}),
            ("suspects", {}),
            ("questions", {"suspect_id": case.suspects[0].id}),
            ("evidence", {}),
            ("comparable", {}),
            ("timeline", {}),
            ("notebook", {}),
            ("assess", {}),
            ("status", {}),
        ]
        for method, payload in checks:
            raw = api(method, json.dumps(payload))
            decoded = json.loads(raw)  # raises if it is not valid JSON
            self.assertTrue(decoded["ok"], f"{method}: {decoded}")

    def test_a_full_case_can_be_played_through_the_web_api_alone(self):
        load_everything()
        SESSION.detective.xp = 99999
        case = SESSION.cases[0]
        api("start", json.dumps({"case_id": case.id}))

        for loc in json.loads(api("locations"))["locations"]:
            room = json.loads(api("enter", json.dumps({"location_id": loc["id"]})))
            for s in room["searchables"]:
                api("search", json.dumps(
                    {"location_id": loc["id"], "searchable_id": s["id"]}))

        for s in json.loads(api("suspects"))["suspects"]:
            for q in json.loads(api("questions", json.dumps({"suspect_id": s["id"]})))["questions"]:
                api("ask", json.dumps({"suspect_id": s["id"], "topic": q["topic"]}))

        dash = json.loads(api("dashboard"))
        self.assertEqual(dash["evidence_found"], dash["evidence_total"])

        result = json.loads(api("accuse", json.dumps({"suspect_id": case.culprit_id})))
        self.assertTrue(result["solved"])
        self.assertGreaterEqual(result["stars"], 3)

    def test_a_locked_case_is_refused(self):
        load_everything()
        SESSION.detective.xp = 0
        locked = next(c for c in json.loads(api("library"))["cases"] if c["locked"])
        result = json.loads(api("start", json.dumps({"case_id": locked["id"]})))
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "CaseLocked")


class TestManifest(unittest.TestCase):
    def test_the_manifest_lists_every_python_file_the_package_needs(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        on_disk = {
            str(p.relative_to(ROOT)).replace("\\", "/")
            for p in (ROOT / "detective_x").rglob("*.py")
        }
        self.assertEqual(set(manifest["python"]), on_disk,
                         "run tools/build_manifest.py")

    def test_the_manifest_lists_every_case(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        on_disk = {p.name for p in (ROOT / "detective_x/data/cases").glob("case_*.json")}
        self.assertEqual(set(manifest["cases"]), on_disk)

    def test_nojekyll_exists(self):
        """Without it, GitHub Pages deletes every file starting with an underscore."""
        self.assertTrue((ROOT / ".nojekyll").exists(),
                        "GitHub Pages would strip __init__.py without .nojekyll")

    def test_every_asset_referenced_by_the_page_exists(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="\./([^"]+)"', html):
            self.assertTrue((ROOT / ref).exists(), f"index.html references missing {ref}")


if __name__ == "__main__":
    unittest.main()

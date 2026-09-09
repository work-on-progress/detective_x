"""The browser-facing facade.

Pyodide holds one Session object and calls its methods. Every method returns
plain data that survives conversion to JavaScript. There is no game logic in
here: it delegates to exactly the same engine the terminal build uses.
"""

from __future__ import annotations

import json

from ..config import APP_NAME, VERSION
from ..engine.analyst import DeductionEngine
from ..engine.investigation import Investigation
from ..engine.loader import load_case_dict
from ..exceptions import DetectiveXError
from ..models.case import Case, Detective
from ..models.enums import CaseStatus
from ..persistence.save_manager import MemoryStorage, SaveManager


def _ok(payload: dict | None = None, **extra) -> dict:
    out = {"ok": True}
    if payload:
        out.update(payload)
    out.update(extra)
    return out


def _fail(exc: Exception) -> dict:
    kind = type(exc).__name__ if isinstance(exc, DetectiveXError) else "UnexpectedError"
    return {"ok": False, "error": str(exc), "kind": kind}


def guarded(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DetectiveXError as exc:
            return _fail(exc)
        except Exception as exc:  # noqa: BLE001 - surfaced to the player, not swallowed
            return _fail(exc)
    return wrapper


class Session:
    """One player, one browser tab."""

    def __init__(self) -> None:
        self.cases: list[Case] = []
        self.analyst: DeductionEngine | None = None
        self.saves = SaveManager(MemoryStorage())
        self.detective = Detective(name="Detective")
        self.investigation: Investigation | None = None
        self.ready = False

    # -- setup -----------------------------------------------------------
    @guarded
    def load_cases(self, payload: str) -> dict:
        """Receive the case files as a JSON array fetched by the browser."""
        raw = json.loads(payload)
        loaded, problems = [], []
        for entry in raw:
            try:
                loaded.append(load_case_dict(entry))
            except DetectiveXError as exc:
                problems.append(str(exc))
        if not loaded:
            return {"ok": False, "error": "; ".join(problems) or "no cases", "kind": "CaseDataError"}
        loaded.sort(key=lambda c: c.id)
        self.cases = loaded
        self.analyst = DeductionEngine(loaded)
        self.ready = True
        return _ok(
            version=VERSION,
            name=APP_NAME,
            count=len(loaded),
            rejected=problems,
        )

    @guarded
    def use_browser_storage(self) -> dict:
        from ..persistence.save_manager import BrowserStorage

        self.saves = SaveManager(BrowserStorage())
        return _ok()

    # -- profile ---------------------------------------------------------
    @guarded
    def profile(self) -> dict:
        d = self.detective
        into, span = d.rank_progress
        return _ok({
            "name": d.name,
            "rank": d.rank.title,
            "next_rank": d.rank.next_rank.title if d.rank.next_rank else None,
            "xp": d.xp,
            "rank_into": into,
            "rank_span": span,
            "cases_won": d.cases_won,
            "cases_lost": d.cases_lost,
            "stars": d.stars,
            "best_score": d.best_score,
            "completed": sorted(d.completed),
            "failed": sorted(d.failed),
        })

    @guarded
    def load_profile(self) -> dict:
        try:
            existing = self.saves.load_profile()
        except DetectiveXError as exc:
            recovered = self.saves.recover(SaveManager.PROFILE_KEY)
            return _ok(recovered=recovered, warning=str(exc), found=False)
        if existing:
            self.detective = existing
            return _ok(found=True)
        return _ok(found=False)

    @guarded
    def set_name(self, name: str) -> dict:
        self.detective.name = (name or "Detective").strip()[:32]
        self.saves.save_profile(self.detective)
        return _ok(name=self.detective.name)

    @guarded
    def reset_profile(self) -> dict:
        self.detective = Detective(name=self.detective.name)
        self.saves.clear_progress()
        self.saves.save_profile(self.detective)
        self.investigation = None
        return _ok()

    # -- case library ----------------------------------------------------
    @guarded
    def library(self) -> dict:
        rows = []
        for case in self.cases:
            head = case.header()
            rows.append({
                **head,
                "locked": self.detective.xp < head["unlock_xp"],
                "solved": case.id in self.detective.completed,
                "failed": case.id in self.detective.failed,
            })
        return _ok(cases=rows, has_progress=self.saves.has_progress())

    @guarded
    def briefing(self, case_id: int) -> dict:
        case = self._case(case_id)
        return _ok({**case.header(), "briefing": case.briefing})

    # -- investigation lifecycle -----------------------------------------
    @guarded
    def start(self, case_id: int, debug: bool = False) -> dict:
        case = self._case(case_id)
        if self.detective.xp < case.difficulty.unlock_xp:
            return {"ok": False, "error": f"{case.title} is not open to you yet.", "kind": "CaseLocked"}
        self.investigation = Investigation(
            case, analyst=self.analyst, seed=1234 if debug else None, debug=debug
        )
        return _ok(self.investigation.dashboard())

    @guarded
    def resume(self) -> dict:
        try:
            state = self.saves.load_progress()
        except DetectiveXError as exc:
            self.saves.recover(SaveManager.PROGRESS_KEY)
            return {"ok": False, "error": str(exc), "kind": "CorruptSaveError"}
        if state is None:
            return {"ok": False, "error": "Nothing is in progress.", "kind": "InvalidChoice"}
        case = next((c for c in self.cases if c.id == state.case_id), None)
        if case is None:
            self.saves.clear_progress()
            return {"ok": False, "error": "That case file is no longer available.", "kind": "CaseDataError"}
        self.investigation = Investigation(case, state=state, analyst=self.analyst)
        return _ok(self.investigation.dashboard())

    @guarded
    def save(self) -> dict:
        inv = self._inv()
        self.saves.save_progress(inv.state)
        self.saves.save_profile(self.detective)
        return _ok()

    @guarded
    def abandon(self) -> dict:
        self.saves.clear_progress()
        self.investigation = None
        return _ok()

    # -- during the case -------------------------------------------------
    @guarded
    def dashboard(self) -> dict:
        return _ok(self._inv().dashboard())

    @guarded
    def locations(self) -> dict:
        return _ok(locations=self._inv().locations())

    @guarded
    def enter(self, location_id: str) -> dict:
        return _ok(self._inv().enter_location(location_id))

    @guarded
    def search(self, location_id: str, searchable_id: str) -> dict:
        inv = self._inv()
        result = inv.search(location_id, searchable_id)
        return _ok(result, dashboard=inv.dashboard())

    @guarded
    def suspects(self) -> dict:
        return _ok(suspects=self._inv().suspects())

    @guarded
    def questions(self, suspect_id: str) -> dict:
        return _ok(questions=self._inv().questions_for(suspect_id))

    @guarded
    def ask(self, suspect_id: str, topic: str) -> dict:
        inv = self._inv()
        result = inv.ask(suspect_id, topic)
        return _ok(result, dashboard=inv.dashboard())

    @guarded
    def evidence(self) -> dict:
        return _ok(evidence=self._inv().evidence_held())

    @guarded
    def comparable(self) -> dict:
        return _ok(evidence=self._inv().comparable_evidence())

    @guarded
    def targets(self, evidence_id: str) -> dict:
        return _ok(targets=self._inv().comparison_targets(evidence_id))

    @guarded
    def compare(self, evidence_id: str, target: str) -> dict:
        inv = self._inv()
        return _ok(inv.compare(evidence_id, target), dashboard=inv.dashboard())

    @guarded
    def timeline(self) -> dict:
        return _ok(timeline=self._inv().timeline())

    @guarded
    def notebook(self) -> dict:
        inv = self._inv()
        return _ok(inv.notebook(), board=inv.board(), reliability=inv.reliability())

    @guarded
    def hint(self) -> dict:
        inv = self._inv()
        return _ok(inv.hint(), dashboard=inv.dashboard())

    @guarded
    def assess(self) -> dict:
        return _ok(self._inv().assess())

    @guarded
    def accuse(self, suspect_id: str) -> dict:
        inv = self._inv()
        result = inv.accuse(suspect_id)

        d = self.detective
        before = d.rank
        d.xp += result["xp"]
        if result["solved"]:
            d.cases_won += 1
            d.completed.add(inv.case.id)
        else:
            d.cases_lost += 1
            d.failed.add(inv.case.id)
        d.best_score = max(d.best_score, result["score"])
        self.saves.save_profile(d)
        self.saves.clear_progress()

        return _ok(result, promoted=(d.rank != before), rank=d.rank.title,
                   previous_rank=before.title)

    @guarded
    def status(self) -> dict:
        inv = self.investigation
        return _ok(
            active=inv is not None and inv.state.status is CaseStatus.IN_PROGRESS,
            case_id=inv.case.id if inv else None,
        )

    # -- internals -------------------------------------------------------
    def _case(self, case_id: int) -> Case:
        case = next((c for c in self.cases if c.id == int(case_id)), None)
        if case is None:
            raise DetectiveXError(f"There is no case number {case_id}.")
        return case

    def _inv(self) -> Investigation:
        if self.investigation is None:
            raise DetectiveXError("No investigation is open.")
        return self.investigation


SESSION = Session()


def api(method: str, payload: str = "{}") -> str:
    """Single JSON-in, JSON-out entry point, so the bridge stays tiny."""
    try:
        kwargs = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": f"bad payload: {exc}", "kind": "InvalidChoice"})
    fn = getattr(SESSION, method, None)
    if fn is None or method.startswith("_"):
        return json.dumps({"ok": False, "error": f"no such method: {method}", "kind": "InvalidChoice"})
    return json.dumps(fn(**kwargs))

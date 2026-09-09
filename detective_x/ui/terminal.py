"""The terminal front-end.

Everything here prints and reads input. Nothing here computes a game outcome —
it calls the engine and displays what comes back. That separation is what lets
the browser build reuse the engine untouched.
"""

from __future__ import annotations

import sys
import time

from ..config import APP_NAME, VERSION
from ..engine.analyst import DeductionEngine
from ..engine.investigation import Investigation
from ..engine.loader import load_all
from ..exceptions import CaseLocked, DetectiveXError, InvalidChoice
from ..models.case import Case, Detective
from ..models.enums import CaseStatus, Difficulty
from ..persistence.save_manager import SaveManager
from . import boxes as B
from . import colours as C

LOGO = r"""
    ____  _____ _____ _____ ____ _____ _____ _   _ _____
   |  _ \| ____|_   _| ____/ ___|_   _|_   _| | | | ____|
   | | | |  _|   | | |  _|| |     | |   | | | | | |  _|
   | |_| | |___  | | | |__| |___  | |   | | | |_| | |___
   |____/|_____| |_| |_____\____| |_|   |_|  \___/|_____|
                                                    X
"""


def prompt_choice(prompt: str, valid: set[str]) -> str:
    """The one input loop. Written once, used everywhere."""
    while True:
        try:
            raw = input(C.paint(prompt, C.CYAN)).strip().lower()
        except EOFError:
            return "0"
        if raw in valid:
            return raw
        print(C.paint("  Not an option here. Try again.", C.GREY))


def pause() -> None:
    try:
        input(C.paint("\n  [Enter] to continue ", C.GREY))
    except EOFError:
        pass


def analysing(label: str = "Analysing", enabled: bool = True, steps: int = 18) -> None:
    if not enabled:
        return
    for i in range(1, steps + 1):
        sys.stdout.write(f"\r  {label} [{B.bar(i, steps, 20)}]")
        sys.stdout.flush()
        time.sleep(0.03)
    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()


class TerminalGame:
    def __init__(self, args) -> None:
        B.enable_windows_unicode()
        if getattr(args, "ascii", False):
            B.use_ascii(True)
        if getattr(args, "no_colour", False):
            C.disable()

        self.animate = not getattr(args, "no_animation", False)
        self.debug = getattr(args, "debug", False)
        self.seed = 1234 if self.debug else None

        self.cases: list[Case] = load_all()
        self.analyst = DeductionEngine(self.cases)
        self.saves = SaveManager(args.storage)
        self.detective = self._load_or_create_profile()
        self.running = True

    # -- profile ---------------------------------------------------------
    def _load_or_create_profile(self) -> Detective:
        try:
            existing = self.saves.load_profile()
        except DetectiveXError as exc:
            print(C.paint(f"\n  {exc}", C.RED))
            if self.saves.recover(SaveManager.PROFILE_KEY):
                print(C.paint("  A backup was restored.", C.GREEN))
                existing = self.saves.load_profile()
            else:
                print(C.paint("  Starting a new profile.", C.AMBER))
                existing = None
        if existing:
            return existing
        B.clear()
        print(C.paint(LOGO, C.AMBER))
        try:
            name = input("  Detective's name: ").strip() or "Detective"
        except EOFError:
            name = "Detective"
        detective = Detective(name=name)
        self.saves.save_profile(detective)
        return detective

    # -- main loop -------------------------------------------------------
    def run(self) -> int:
        while self.running:
            self.main_menu()
        print(C.paint("\n  Case closed for tonight.\n", C.GREY))
        return 0

    def main_menu(self) -> None:
        B.clear()
        print(C.paint(LOGO, C.AMBER))
        d = self.detective
        into, span = d.rank_progress
        print(B.draw_box(
            f"{d.name} — {d.rank.title}",
            B.columns([
                ("Cases solved", str(d.cases_won)),
                ("Cases failed", str(d.cases_lost)),
                ("Experience", f"{B.bar(into, span, 12)} {d.xp}"),
                ("Rating", B.stars(d.stars)),
            ], B.terminal_width()),
            style="double",
        ))
        options = [
            "[1] Open a case file",
            "[2] Resume the current investigation" if self.saves.has_progress() else "[2] Resume (nothing in progress)",
            "[3] Case records",
            "[4] How to investigate",
            "[5] Quit",
        ]
        print(B.draw_box("Main menu", options, style="single"))
        choice = prompt_choice("  > ", {"1", "2", "3", "4", "5"})

        if choice == "1":
            self.case_library()
        elif choice == "2":
            self.resume()
        elif choice == "3":
            self.records()
        elif choice == "4":
            self.help_screen()
        else:
            self.running = False

    # -- case library ----------------------------------------------------
    def case_library(self) -> None:
        B.clear()
        rows = []
        valid = {"0"}
        for i, case in enumerate(self.cases, start=1):
            locked = self.detective.xp < case.difficulty.unlock_xp
            solved = case.id in self.detective.completed
            mark = "SOLVED" if solved else ("LOCKED" if locked else "")
            rows.append(
                f"[{i:2d}] {B.pad(case.title, 30)} {B.pad(case.difficulty.value, 8)} {mark}"
            )
            if not locked:
                valid.add(str(i))
        rows.append("---")
        rows.append("[ 0] Back")
        print(B.draw_box("Case files", rows, style="double"))
        choice = prompt_choice("  Open case > ", valid)
        if choice == "0":
            return
        case = self.cases[int(choice) - 1]
        if self.detective.xp < case.difficulty.unlock_xp:
            raise CaseLocked(case.title)
        self.brief_and_play(case)

    def brief_and_play(self, case: Case) -> None:
        B.clear()
        head = case.header()
        print(B.draw_box(
            case.title.upper(),
            B.columns([
                ("Location", head["setting"]),
                ("Offence", head["crime"]),
                ("Window", head["window"]),
                ("Suspects", str(head["suspects"])),
                ("Difficulty", head["difficulty"]),
            ], B.terminal_width()) + ["---", case.briefing],
            style="double",
        ))
        pause()
        investigation = Investigation(
            case, analyst=self.analyst, seed=self.seed, debug=self.debug
        )
        self.investigate(investigation)

    def resume(self) -> None:
        try:
            state = self.saves.load_progress()
        except DetectiveXError as exc:
            print(C.paint(f"\n  {exc}", C.RED))
            self.saves.recover(SaveManager.PROGRESS_KEY)
            pause()
            return
        if state is None:
            print(C.paint("\n  Nothing is in progress.", C.GREY))
            pause()
            return
        case = next((c for c in self.cases if c.id == state.case_id), None)
        if case is None:
            print(C.paint("\n  That case file is no longer available.", C.RED))
            self.saves.clear_progress()
            pause()
            return
        self.investigate(
            Investigation(case, state=state, analyst=self.analyst, seed=self.seed)
        )

    # -- investigation ---------------------------------------------------
    def investigate(self, inv: Investigation) -> None:
        while inv.state.status is CaseStatus.IN_PROGRESS:
            B.clear()
            self.dashboard(inv)
            choice = prompt_choice(
                "  Action > ",
                {"1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "0"},
            )
            try:
                self.dispatch(inv, choice)
            except InvalidChoice as exc:
                print(C.paint(f"  {exc}", C.AMBER))
                pause()
            if choice == "0":
                return

    def dashboard(self, inv: Investigation) -> None:
        d = inv.dashboard()
        print(B.draw_box(
            d["case"]["title"].upper(),
            B.columns([
                ("Detective", self.detective.name),
                ("Difficulty", d["difficulty"]),
                ("Evidence", f"{d['evidence_found']} of {d['evidence_total']}"),
                ("Locations", f"{d['locations_visited']} of {d['locations_total']}"),
                ("Contradictions", str(d["contradictions"])),
                ("Hints left", str(d["hints_remaining"])),
                ("Score", f"{d['score']} / {d['par']}"),
                ("Progress", f"{B.bar(d['completion'], 100, 16)} {d['completion']}%"),
            ], B.terminal_width()),
            style="double",
        ))
        print(B.draw_box(None, [
            "[1] Visit a location        [6] Crime timeline",
            "[2] Question a suspect      [7] Compare evidence",
            "[3] Examine evidence        [8] Request a hint",
            "[4] Suspect profiles        [9] Make an accusation",
            "[5] Notebook                [a] Deduction engine",
            "[0] Save and leave",
        ], style="single"))

    def dispatch(self, inv: Investigation, choice: str) -> None:
        actions = {
            "1": self.locations,
            "2": self.questioning,
            "3": self.evidence,
            "4": self.profiles,
            "5": self.notebook,
            "6": self.timeline,
            "7": self.comparison,
            "8": self.hint,
            "9": self.accusation,
            "a": self.analysis,
            "0": self.save_and_exit,
        }
        actions[choice](inv)

    def locations(self, inv: Investigation) -> None:
        B.clear()
        locs = inv.locations()
        rows, valid = [], {"0"}
        for i, loc in enumerate(locs, start=1):
            state = "exhausted" if loc["exhausted"] else f"{loc['searched']}/{loc['searchable_count']} searched"
            rows.append(f"[{i}] {B.pad(loc['icon'] + ' ' + loc['name'], 30)} {state}")
            valid.add(str(i))
        rows += ["---", "[0] Back"]
        print(B.draw_box("Where to?", rows, style="single"))
        pick = prompt_choice("  > ", valid)
        if pick == "0":
            return
        self.explore(inv, locs[int(pick) - 1]["id"])

    def explore(self, inv: Investigation, location_id: str) -> None:
        while True:
            B.clear()
            room = inv.enter_location(location_id)
            rows, valid = [room["description"], "---"], {"0"}
            for i, s in enumerate(room["searchables"], start=1):
                tick = "done" if s["searched"] else ""
                rows.append(f"[{i}] {B.pad(s['label'], 34)} {tick}")
                valid.add(str(i))
            rows += ["---", "[0] Leave"]
            print(B.draw_box(f"{room['icon']}  {room['name'].upper()}", rows, style="double"))
            pick = prompt_choice("  > ", valid)
            if pick == "0":
                return
            sid = room["searchables"][int(pick) - 1]["id"]
            analysing("Searching", self.animate)
            result = inv.search(location_id, sid)
            self.show_search(result)
            pause()

    def show_search(self, result: dict) -> None:
        lines = []
        if result["flavour"]:
            lines.append(result["flavour"])
        if result["repeat"]:
            lines.append(C.paint("You have been over this already. (-10)", C.GREY))
        for ev in result["found"]:
            lines += [
                "---",
                C.paint(f"RECOVERED  {ev['name']}", C.GREEN),
                ev["description"],
                f"{ev['type']} · {ev['reliability']}% reliable",
            ]
        for ev in result["unlocked"]:
            lines += [
                "---",
                C.paint(f"THIS OPENS UP  {ev['name']}", C.AMBER),
                ev["description"],
            ]
        if not result["found"] and not result["unlocked"] and not result["repeat"]:
            lines.append("Nothing of use here.")
        if result.get("ambient"):
            lines += ["---", C.paint(result["ambient"], C.GREY)]
        if result["delta"]:
            lines.append(f"Score {result['delta']:+d}")
        print(B.draw_box("Search", lines, style="single"))

    def questioning(self, inv: Investigation) -> None:
        B.clear()
        people = inv.suspects()
        rows, valid = [], {"0"}
        for i, s in enumerate(people, start=1):
            meter = "" if s["suspicion"] is None else f"{B.bar(s['suspicion'], 100, 10)} {s['suspicion']}%"
            rows.append(f"[{i}] {B.pad(s['name'], 24)} {meter}")
            valid.add(str(i))
        rows += ["---", "[0] Back"]
        print(B.draw_box("Who do you want to speak to?", rows, style="single"))
        pick = prompt_choice("  > ", valid)
        if pick == "0":
            return
        self.interview(inv, people[int(pick) - 1]["id"])

    def interview(self, inv: Investigation, suspect_id: str) -> None:
        while True:
            B.clear()
            qs = inv.questions_for(suspect_id)
            name = next(s["name"] for s in inv.suspects() if s["id"] == suspect_id)
            rows, valid = [], {"0"}
            for i, q in enumerate(qs, start=1):
                mark = "asked" if q["asked"] else ("new" if q["unlocked"] else "")
                rows.append(f"[{i}] {B.pad(q['question'], 46)} {mark}")
                valid.add(str(i))
            rows += ["---", "[0] End the interview"]
            print(B.draw_box(f"INTERVIEW — {name.upper()}", rows, style="double"))
            pick = prompt_choice("  > ", valid)
            if pick == "0":
                return
            answer = inv.ask(suspect_id, qs[int(pick) - 1]["topic"])
            lines = [f"\"{answer['answer']}\""]
            for c in answer["new_contradictions"]:
                lines += ["---", C.paint(f"CONTRADICTION — {c['suspect']} on {c['topic']}", C.RED)]
                lines.append(f"They say: {c['claim']}")
                for other in c["contradicted_by"]:
                    lines.append(f"{other['name']} says: {other['text']}")
                lines.append(f"Suspicion +{c['penalty']}")
            print(B.draw_box(name, lines, style="single"))
            pause()

    def evidence(self, inv: Investigation) -> None:
        B.clear()
        held = inv.evidence_held()
        if not held:
            print(B.draw_box("Evidence", ["You are not carrying anything yet."], style="single"))
            pause()
            return
        lines = []
        for ev in held:
            tag = C.paint(" CLEARED", C.GREY) if ev["cleared"] else ""
            lines += [
                f"{ev['name']}{tag}",
                f"  {ev['description']}",
                f"  {ev['type']} · {B.bar(ev['reliability'], 100, 10)} {ev['reliability']}%",
                "---",
            ]
        print(B.draw_box("Evidence held", lines[:-1], style="double"))
        pause()

    def profiles(self, inv: Investigation) -> None:
        B.clear()
        for s in inv.suspects():
            meter = [] if s["suspicion"] is None else [
                f"Suspicion  {B.bar(s['suspicion'], 100, 14)} {s['suspicion']}%"
            ]
            print(B.draw_box(s["name"].upper(), [
                f"{s['occupation']}, age {s['age']}",
                s["relation"],
                "---",
                f"Motive: {s['motive']}",
                *meter,
            ], style="round"))
        pause()

    def notebook(self, inv: Investigation) -> None:
        B.clear()
        nb = inv.notebook()
        lines = [C.paint("Established", C.GREEN)]
        lines += [f"  + {n}" for n in nb["confirmed"]] or ["  Nothing yet."]
        if nb["open"]:
            lines += ["---", C.paint("Still open", C.AMBER)]
            lines += [f"  ? {n}" for n in nb["open"]]
        print(B.draw_box("Notebook", lines, style="double"))
        board = inv.board()
        if board:
            rows = []
            for entry in board:
                rows.append(entry["suspect"].upper())
                for t in entry["threads"]:
                    mark = "(cleared)" if t["cleared"] else f"+{t['weight']}"
                    rows.append(f"   └─ {B.pad(t['label'], 40)} {mark}")
                rows.append("---")
            print(B.draw_box("Evidence board", rows[:-1], style="single"))
        pause()

    def timeline(self, inv: Investigation) -> None:
        B.clear()
        rows = []
        for e in inv.timeline():
            mark = C.paint(" ←uncovered", C.AMBER) if e["revealed"] else ""
            rows.append(f"{B.pad(e['time'], 10)} ─ {e['text']}{mark}")
        print(B.draw_box("Timeline", rows or ["Nothing established yet."], style="double"))
        pause()

    def comparison(self, inv: Investigation) -> None:
        B.clear()
        held = inv.comparable_evidence()
        if not held:
            print(B.draw_box("Compare", [
                "Nothing you are carrying can be matched against a belonging.",
                "Trace evidence — fibres, buttons, prints, print defects — can be.",
            ], style="single"))
            pause()
            return
        rows, valid = [], {"0"}
        for i, ev in enumerate(held, start=1):
            rows.append(f"[{i}] {ev['name']}")
            valid.add(str(i))
        rows += ["---", "[0] Back"]
        print(B.draw_box("Compare which clue?", rows, style="single"))
        pick = prompt_choice("  > ", valid)
        if pick == "0":
            return
        eid = held[int(pick) - 1]["id"]

        targets = inv.comparison_targets(eid)
        rows, valid = [], {"0"}
        for i, t in enumerate(targets, start=1):
            rows.append(f"[{i}] {t}")
            valid.add(str(i))
        rows += ["---", "[0] Back"]
        print(B.draw_box("Against what?", rows, style="single"))
        pick = prompt_choice("  > ", valid)
        if pick == "0":
            return
        analysing("Comparing", self.animate)
        result = inv.compare(eid, targets[int(pick) - 1])
        colour = C.GREEN if result["match"] else C.GREY
        print(B.draw_box("Match analysis", B.columns([
            ("Evidence", result["evidence"]),
            ("Compared with", result["target"]),
            ("Result", C.paint(result["verdict"], colour)),
            ("Confidence", f"{result['confidence']}%"),
        ], B.terminal_width()), style="double"))
        pause()

    def hint(self, inv: Investigation) -> None:
        B.clear()
        print(B.draw_box("Assistance", [
            f"Hints remaining : {inv.state.hints_remaining}",
            "Score penalty   : -50",
            "---",
            "Use one? [y/n]",
        ], style="single"))
        if prompt_choice("  > ", {"y", "n"}) == "n":
            return
        result = inv.hint()
        print(B.draw_box("Hint", [result["text"]], style="double"))
        pause()

    def analysis(self, inv: Investigation) -> None:
        B.clear()
        analysing("Running the model", self.animate, steps=24)
        result = inv.assess()
        if not result.get("available"):
            print(B.draw_box("Deduction engine", ["The model is unavailable."], style="single"))
            pause()
            return
        rows = [
            f"Trained on {result['trained_on']} other cases, {result['samples']} suspects.",
            f"Evidence coverage {result['coverage']}% · Certainty: {result['certainty']}",
            "---",
        ]
        for r in result["ranking"]:
            rows.append(f"{B.pad(r['name'], 22)} {B.bar(round(r['share']), 100, 14)} {r['share']:5.1f}%")
        top = result["ranking"][0]
        if top["drivers"]:
            rows += ["---", f"What drives the figure for {top['name']}:"]
            rows += [f"   {d['feature']}: {d['impact']:+.2f}" for d in top["drivers"]]
        rows += ["---", C.paint("The model is a guide, not a verdict. It has been wrong.", C.GREY)]
        print(B.draw_box("Deduction engine", rows, style="double"))
        pause()

    def accusation(self, inv: Investigation) -> None:
        B.clear()
        people = inv.suspects()
        rows, valid = ["This will close the investigation.", "---"], {"0"}
        for i, s in enumerate(people, start=1):
            rows.append(f"[{i}] {s['name']}")
            valid.add(str(i))
        rows += ["---", "[0] Not yet"]
        print(B.draw_box("Final accusation", rows, style="double"))
        pick = prompt_choice("  > ", valid)
        if pick == "0":
            return
        chosen = people[int(pick) - 1]
        print(C.paint(f"\n  Accuse {chosen['name']}? [y/n]", C.AMBER))
        if prompt_choice("  > ", {"y", "n"}) == "n":
            return

        analysing("Filing the report", self.animate, steps=26)
        result = inv.accuse(chosen["id"])
        self.finish(inv, result)

    def finish(self, inv: Investigation, result: dict) -> None:
        B.clear()
        if result["solved"]:
            title, colour = "CASE SOLVED", C.GREEN
        else:
            title, colour = "WRONG ACCUSATION", C.RED

        rows = B.columns([
            ("Culprit", result["culprit"]),
            ("You accused", result["accused"]),
            ("Score", f"{result['score']} of {result['par']} ({result['percent']}%)"),
            ("Evidence", f"{result['evidence_found']} of {result['evidence_total']}"),
            ("Contradictions", str(result["contradictions"])),
            ("Hints used", str(result["hints_used"])),
            ("Experience", f"+{result['xp']}"),
            ("Rating", B.stars(result["stars"])),
        ], B.terminal_width())
        print(B.draw_box(C.paint(title, colour), rows, style="double"))

        if result["missed"]:
            print(B.draw_box("What you did not find", [f"• {m}" for m in result["missed"]], style="single"))

        print(B.draw_box("What actually happened", [result["solution"]], style="single"))

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
        if d.rank != before:
            print(B.draw_box("Promotion", [
                f"{before.title}  →  {d.rank.title}",
            ], style="round"))

        self.saves.save_profile(d)
        self.saves.clear_progress()
        pause()

    def save_and_exit(self, inv: Investigation) -> None:
        self.saves.save_progress(inv.state)
        self.saves.save_profile(self.detective)
        print(C.paint("\n  Progress saved.", C.GREEN))
        pause()

    # -- other screens ---------------------------------------------------
    def records(self) -> None:
        B.clear()
        d = self.detective
        rows = []
        for case in self.cases:
            if case.id in d.completed:
                mark = C.paint("solved", C.GREEN)
            elif case.id in d.failed:
                mark = C.paint("failed", C.RED)
            else:
                mark = C.paint("open", C.GREY)
            rows.append(f"{B.pad(case.title, 32)} {mark}")
        print(B.draw_box("Case records", rows, style="double"))
        pause()

    def help_screen(self) -> None:
        B.clear()
        print(B.draw_box("How to investigate", [
            "Search every location. Clues are hidden inside objects, not rooms.",
            "",
            "Question everyone about the same topics. Two people describing the "
            "same moment differently is a contradiction, and contradictions are "
            "worth more than clues.",
            "",
            "Watch reliability. A 72% witness statement counts for less than a "
            "100% access log, and the scoring reflects that.",
            "",
            "Some clues are red herrings. Find the clue that clears them and "
            "they stop counting against the wrong person.",
            "",
            "Some clues unlock others. If a search yields nothing, you may be "
            "missing a prerequisite rather than looking in the wrong place.",
            "",
            "The deduction engine is a machine learning model trained on the "
            "other cases in the file. It is a guide, not a verdict.",
            "---",
            f"{APP_NAME} {VERSION}",
        ], style="double"))
        pause()

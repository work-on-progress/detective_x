/* Detective X — browser front-end.
 *
 * This file renders and reacts. It computes no scores, resolves no
 * contradictions and decides no outcomes: every one of those comes back from
 * the Python engine, which is the same engine the terminal build runs.
 */

import { Bridge } from "./bridge.js";

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, props = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    // Hyphenated names (aria-*, data-*) are attributes, not properties.
    // Object.assign would quietly create a useless expando instead.
    if (key.includes("-")) node.setAttribute(key, String(value));
    else node[key] = value;
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
};

const State = {
  view: "library",
  caseOpen: false,
  currentCase: null,
  locationId: null,
  suspectId: null,
  evidenceId: null,
  dashboard: null,
  profile: null,
};

/* ------------------------------------------------------------------ boot */
async function boot() {
  const bar = $("#bootbar");
  const msg = $("#bootmsg");
  try {
    await Bridge.boot((pct, text) => {
      bar.style.width = `${pct}%`;
      msg.textContent = text;
    });
  } catch (err) {
    msg.innerHTML = "";
    msg.append(
      el("p", { className: "typed" }, `The engine did not start: ${err.message}`),
      el("p", { className: "typed muted" },
        "Reload the page. If it keeps happening, the browser may be blocking the Python runtime.")
    );
    return;
  }
  $("#boot").remove();
  $("#app").hidden = false;
  refreshProfile();
  render();
}

/* --------------------------------------------------------------- helpers */
function toast(text, kind = "") {
  const node = el("div", { className: `toast ${kind}` }, text);
  $("#toasts").append(node);
  setTimeout(() => node.remove(), 4200);
}

function guard(result) {
  if (result && result.ok === false) {
    toast(result.error, "bad");
    return null;
  }
  return result;
}

function refreshProfile() {
  const p = guard(Bridge.call("profile"));
  if (p) State.profile = p;
}

function meter(value, total, tone = "") {
  const pct = total ? Math.max(0, Math.min(100, (value / total) * 100)) : 0;
  return el("div", { className: `meter ${tone}` }, el("i", { style: `width:${pct}%` }));
}

function stars(n) {
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function closeModal() {
  $("#overlay").innerHTML = "";
  $("#overlay").hidden = true;
}

function modal(title, body, actions = []) {
  const box = el("div", { className: "modal paper" },
    el("div", { className: "stage-head" },
      el("div", {}, el("h2", {}, title)),
      el("button", { className: "btn ghost", onclick: closeModal }, "Close")),
    body,
    actions.length ? el("div", { className: "modal-actions" }, ...actions) : null
  );
  const overlay = $("#overlay");
  overlay.innerHTML = "";
  overlay.hidden = false;
  overlay.append(box);
  overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
  const first = box.querySelector("button:not(.ghost), input");
  if (first) first.focus();
  return box;
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#overlay").hidden) closeModal();
});

/* ---------------------------------------------------------------- render */
function render() {
  renderTopbar();
  const folder = $("#folder");
  folder.innerHTML = "";
  folder.classList.toggle("single", !State.caseOpen);

  if (State.caseOpen) folder.append(renderRail());
  folder.append(el("section", { className: "stage paper", id: "stage" }, views[State.view]()));
}

function renderTopbar() {
  const bar = $("#topbar");
  bar.innerHTML = "";
  const tabs = [
    ["library", "Case files", true],
    ["dossier", "Dossier", State.caseOpen],
    ["profile", "Record", true],
    ["about", "Method", true],
  ];
  for (const [id, label, enabled] of tabs) {
    bar.append(el("button", {
      className: "tab",
      role: "tab",
      disabled: !enabled,
      "aria-selected": String(State.view === id || (id === "dossier" && isCaseView(State.view))),
      onclick: () => go(id === "dossier" ? "locations" : id),
    }, label));
  }
  bar.append(el("div", { className: "spacer" }));
  const p = State.profile;
  if (p) {
    bar.append(el("div", { className: "badge" },
      el("b", {}, p.name), el("span", {}, p.rank),
      el("span", { className: "tabular" }, `${p.xp} XP`)));
  }
}

const CASE_VIEWS = new Set([
  "locations", "room", "suspects", "interview", "evidence",
  "timeline", "notebook", "analyst", "accuse",
]);
const isCaseView = (v) => CASE_VIEWS.has(v);

function go(view) {
  State.view = view;
  render();
  window.scrollTo({ top: 0, behavior: "instant" });
}

/* ------------------------------------------------------------------ rail */
function renderRail() {
  const d = State.dashboard;
  const rail = el("aside", { className: "rail" });
  if (!d) return rail;

  rail.append(el("div", { className: "status paper" },
    el("div", { className: "label" }, "Investigation"),
    el("h3", { style: "margin:.3rem 0 .6rem" }, d.case.title),
    row("Evidence", `${d.evidence_found} / ${d.evidence_total}`),
    meter(d.evidence_found, d.evidence_total),
    row("Contradictions", d.contradictions),
    row("Score", `${d.score} / ${d.par}`),
    meter(d.score, d.par, d.score / d.par > 0.6 ? "good" : ""),
    row("Hints left", d.hints_remaining),
    row("Progress", `${d.completion}%`),
    meter(d.completion, 100)
  ));

  const actions = el("nav", { className: "actions paper" });
  const items = [
    ["1", "Locations", "locations"],
    ["2", "Interviews", "suspects"],
    ["3", "Evidence", "evidence"],
    ["4", "Timeline", "timeline"],
    ["5", "Notebook", "notebook"],
    ["6", "Deduction engine", "analyst"],
  ];
  for (const [key, label, view] of items) {
    actions.append(el("button", {
      "aria-current": String(State.view === view),
      onclick: () => go(view),
    }, el("span", { className: "key" }, key), label));
  }
  actions.append(el("div", { className: "divider" }));
  actions.append(el("button", { onclick: askHint },
    el("span", { className: "key" }, "H"), "Request a hint"));
  actions.append(el("button", { onclick: () => go("accuse") },
    el("span", { className: "key" }, "!"), "Make an accusation"));
  actions.append(el("div", { className: "divider" }));
  actions.append(el("button", { onclick: saveAndClose },
    el("span", { className: "key" }, "S"), "Save and close file"));
  rail.append(actions);
  return rail;
}

function row(label, value) {
  return el("div", { className: "row" }, el("span", {}, label), el("span", {}, String(value)));
}

function head(title, note) {
  return el("div", { className: "stage-head" },
    el("div", {}, el("div", { className: "label" }, "Detective X"), el("h1", {}, title)),
    note ? el("div", { className: "stamp" }, note) : null);
}

/* ----------------------------------------------------------------- views */
const views = {};

views.library = () => {
  const data = guard(Bridge.call("library"));
  const wrap = el("div", {}, head("Case files", `${data ? data.cases.length : 0} on file`));
  if (!data) return wrap;

  if (data.has_progress) {
    wrap.append(el("div", { className: "card sheet" },
      el("div", { className: "card-head" },
        el("h3", {}, "An investigation is still open"),
        el("button", { className: "btn", onclick: resumeCase }, "Resume")),
      el("p", { className: "typed muted", style: "margin:.4rem 0 0" },
        "Your last case was saved before you closed the file.")));
  }

  const list = el("div", { className: "list" });
  for (const c of data.cases) {
    const state = c.solved ? "solved" : c.failed ? "reopened" : c.locked ? `${c.unlock_xp} XP` : "open";
    const cls = c.solved ? "entry done" : c.locked ? "entry" : "entry";
    list.append(el("button", {
      className: cls,
      disabled: c.locked,
      onclick: () => openBriefing(c.id),
    },
      el("span", { className: "idx tabular" }, String(c.id).padStart(2, "0")),
      el("span", {},
        el("span", { className: "title" }, c.title),
        el("span", { className: "sub" }, c.subtitle)),
      el("span", { className: "meta" }, `${c.difficulty} · ${state}`)));
  }
  wrap.append(list);
  return wrap;
};

views.profile = () => {
  const p = State.profile;
  const wrap = el("div", {}, head("Service record", p.rank));
  wrap.append(el("div", { className: "grid2" },
    stat("Cases solved", p.cases_won),
    stat("Cases failed", p.cases_lost),
    stat("Experience", p.xp),
    stat("Best score", p.best_score),
    stat("Rating", stars(p.stars)),
    stat("Next rank", p.next_rank ?? "—")));

  if (p.next_rank) {
    wrap.append(el("div", { className: "card sheet" },
      el("div", { className: "label" }, `Progress to ${p.next_rank}`),
      meter(p.rank_into, p.rank_span)));
  }

  wrap.append(el("div", { className: "card sheet" },
    el("h3", {}, "Your name on the file"),
    el("div", { style: "display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.5rem" },
      el("input", { type: "text", id: "namefield", value: p.name, maxLength: 32 }),
      el("button", {
        className: "btn",
        onclick: () => {
          guard(Bridge.call("set_name", { name: $("#namefield").value }));
          refreshProfile();
          render();
        },
      }, "Save"))));

  wrap.append(el("div", { className: "card sheet" },
    el("h3", {}, "Start again"),
    el("p", { className: "typed muted" },
      "This clears your rank, your record and any open investigation. It cannot be undone."),
    el("button", {
      className: "btn danger",
      style: "margin-top:.6rem",
      onclick: () => modal("Clear your record?",
        el("p", { className: "typed" }, "Everything on file is erased and every case returns to its locked state."),
        [el("button", {
          className: "btn danger", onclick: () => {
            guard(Bridge.call("reset_profile"));
            State.caseOpen = false;
            refreshProfile();
            closeModal();
            go("library");
          },
        }, "Clear it"),
         el("button", { className: "btn ghost", onclick: closeModal }, "Keep it")]),
    }, "Clear record")));
  return wrap;
};

function stat(label, value) {
  return el("div", { className: "card sheet" },
    el("div", { className: "label" }, label),
    el("div", { style: "font-size:1.5rem;font-weight:700", className: "tabular" }, String(value)));
}

views.about = () => {
  const wrap = el("div", {}, head("How to investigate"));
  const para = (t) => el("p", { className: "typed brief" }, t);
  wrap.append(
    el("div", { className: "card sheet" },
      el("h3", {}, "Search objects, not rooms"),
      para("Clues live inside things: a floor, a drawer, a log, a bin. Entering a location shows you what can be examined. Searching the same thing twice costs you points.")),
    el("div", { className: "card sheet" },
      el("h3", {}, "Ask everyone the same questions"),
      para("Suspects answer on shared topics. When two accounts of the same moment disagree, that is a contradiction, and contradictions are worth more than clues. You only find one by hearing both sides.")),
    el("div", { className: "card sheet" },
      el("h3", {}, "Weigh reliability"),
      para("A witness who is 72 per cent reliable counts for less than an access log that is certain. The scoring reflects this, and so does the suspicion calculation.")),
    el("div", { className: "card sheet" },
      el("h3", {}, "Expect red herrings"),
      para("Some clues point firmly at the wrong person. Somewhere there is another clue that clears them. Until you find it, the wrong suspect will keep rising to the top.")),
    el("div", { className: "card sheet" },
      el("h3", {}, "Some clues unlock others"),
      para("If a search turns up nothing, you may be missing a prerequisite rather than looking in the wrong place. Chained evidence appears on its own once you hold everything it needs.")),
    el("div", { className: "card sheet" },
      el("h3", {}, "The deduction engine"),
      para("A machine learning model, written from scratch in Python, is trained on the other cases in the file and ranks the suspects for you. It is trained without ever seeing the case you are working on, so it can be wrong. Treat it as a colleague's opinion, not a verdict."))
  );
  return wrap;
};

/* ------------------------------------------------------- case lifecycle */
function openBriefing(caseId) {
  const b = guard(Bridge.call("briefing", { case_id: caseId }));
  if (!b) return;
  const body = el("div", {},
    el("div", { className: "grid2", style: "margin-bottom:1rem" },
      stat("Location", b.setting), stat("Offence", b.crime),
      stat("Window", b.window), stat("Suspects", b.suspects)),
    el("p", { className: "typed brief" }, b.briefing));
  modal(b.title, body, [
    el("button", { className: "btn", onclick: () => startCase(caseId) }, "Open the file"),
    el("button", { className: "btn ghost", onclick: closeModal }, "Not yet"),
  ]);
}

function startCase(caseId) {
  const r = guard(Bridge.call("start", { case_id: caseId }));
  if (!r) return;
  State.dashboard = r;
  State.currentCase = r.case;
  State.caseOpen = true;
  closeModal();
  go("locations");
  const s = el("div", { className: "stamp big land" }, "File opened");
  $("#stage").prepend(el("div", { style: "text-align:right;margin-bottom:.6rem" }, s));
}

function resumeCase() {
  const r = guard(Bridge.call("resume"));
  if (!r) return;
  State.dashboard = r;
  State.currentCase = r.case;
  State.caseOpen = true;
  go("locations");
}

function saveAndClose() {
  guard(Bridge.call("save"));
  State.caseOpen = false;
  toast("Progress saved. The file is closed.", "good");
  go("library");
}

function syncDashboard(result) {
  if (result && result.dashboard) State.dashboard = result.dashboard;
}

/* ------------------------------------------------------------- locations */
views.locations = () => {
  const data = guard(Bridge.call("locations"));
  const wrap = el("div", {}, head(State.currentCase.title, "Locations"));
  if (!data) return wrap;
  const list = el("div", { className: "list" });
  for (const loc of data.locations) {
    const done = loc.exhausted;
    list.append(el("button", {
      className: `entry ${done ? "done" : ""}`,
      onclick: () => { State.locationId = loc.id; go("room"); },
    },
      el("span", { className: "idx" }, loc.icon),
      el("span", {},
        el("span", { className: "title" }, loc.name),
        el("span", { className: "sub" }, loc.description)),
      el("span", { className: "meta" },
        done ? "searched" : `${loc.searched}/${loc.searchable_count}`)));
  }
  wrap.append(list);
  return wrap;
};

views.room = () => {
  const room = guard(Bridge.call("enter", { location_id: State.locationId }));
  const wrap = el("div", {});
  if (!room) return wrap;
  wrap.append(el("div", { className: "stage-head" },
    el("div", {},
      el("div", { className: "label" }, "Location"),
      el("h1", {}, room.name),
      el("p", { className: "typed brief", style: "margin:.6rem 0 0" }, room.description)),
    el("button", { className: "btn ghost", onclick: () => go("locations") }, "Back")));

  const list = el("div", { className: "list" });
  for (const s of room.searchables) {
    list.append(el("button", {
      className: `entry ${s.searched ? "done" : ""}`,
      onclick: () => doSearch(s.id),
    },
      el("span", { className: "idx" }, s.searched ? "✓" : "?"),
      el("span", { className: "title" }, s.label),
      el("span", { className: "meta" }, s.searched ? "searched" : "")));
  }
  wrap.append(list);
  return wrap;
};

function doSearch(searchableId) {
  const r = guard(Bridge.call("search", {
    location_id: State.locationId, searchable_id: searchableId,
  }));
  if (!r) return;
  syncDashboard(r);

  const body = el("div", {});
  if (r.flavour) body.append(el("p", { className: "typed brief" }, r.flavour));
  if (r.repeat) body.append(el("p", { className: "typed muted" }, "You have already been through this. Ten points lost."));

  for (const ev of r.found) body.append(evidenceCard(ev, "Recovered"));
  for (const ev of r.unlocked) body.append(evidenceCard(ev, "This opens up"));
  if (!r.repeat && !r.found.length && !r.unlocked.length) {
    body.append(el("p", { className: "typed muted" }, "Nothing of use here."));
  }
  if (r.ambient) body.append(el("p", { className: "typed muted" }, r.ambient));
  if (r.delta) {
    body.append(el("p", { className: "label", style: "margin-top:.8rem" },
      `Score ${r.delta > 0 ? "+" : ""}${r.delta}`));
  }
  modal("Search", body, [el("button", { className: "btn", onclick: () => { closeModal(); render(); } }, "Continue")]);
}

function evidenceCard(ev, banner) {
  return el("div", { className: "card sheet" },
    el("div", { className: "card-head" },
      el("h3", {}, ev.name),
      el("span", { className: `stamp ${banner === "Recovered" ? "green" : ""}` }, banner)),
    el("p", { className: "typed", style: "margin:.4rem 0 .6rem" }, ev.description),
    el("div", { style: "display:flex;align-items:center;gap:.6rem;flex-wrap:wrap" },
      el("span", { className: `evidence-tag ${String(ev.type).toLowerCase()}` }, ev.type),
      el("span", { className: "label" }, `${ev.reliability}% reliable`),
      el("div", { style: "flex:1;min-width:6rem" }, meter(ev.reliability, 100))));
}

/* ------------------------------------------------------------ interviews */
views.suspects = () => {
  const data = guard(Bridge.call("suspects"));
  const wrap = el("div", {}, head(State.currentCase.title, "Interviews"));
  if (!data) return wrap;
  const list = el("div", { className: "list" });
  for (const s of data.suspects) {
    const hot = s.suspicion != null && s.suspicion >= 70;
    list.append(el("button", {
      className: `entry ${hot ? "hot" : ""}`,
      onclick: () => { State.suspectId = s.id; go("interview"); },
    },
      el("span", { className: "idx" }, s.name.split(" ").map((w) => w[0]).join("").slice(0, 2)),
      el("span", {},
        el("span", { className: "title" }, s.name),
        el("span", { className: "sub" }, `${s.occupation} · ${s.relation}`)),
      el("span", { className: "meta" },
        s.suspicion == null ? `${s.questions_asked}/${s.questions_available}` : `${s.suspicion}%`)));
  }
  wrap.append(list);
  if (data.suspects.some((s) => s.suspicion == null)) {
    wrap.append(el("p", { className: "typed muted", style: "margin-top:1rem" },
      "This case runs without a suspicion meter. You will have to keep score yourself."));
  }
  return wrap;
};

views.interview = () => {
  const people = guard(Bridge.call("suspects"));
  const qs = guard(Bridge.call("questions", { suspect_id: State.suspectId }));
  const wrap = el("div", {});
  if (!people || !qs) return wrap;
  const person = people.suspects.find((s) => s.id === State.suspectId);

  wrap.append(el("div", { className: "stage-head" },
    el("div", {},
      el("div", { className: "label" }, "Interview"),
      el("h1", {}, person.name),
      el("p", { className: "typed", style: "margin:.4rem 0 0" },
        `${person.occupation}, age ${person.age} · ${person.relation}`)),
    el("button", { className: "btn ghost", onclick: () => go("suspects") }, "Back")));

  wrap.append(el("div", { className: "card sheet" },
    el("div", { className: "label" }, "Motive on file"),
    el("p", { className: "typed", style: "margin:.3rem 0 0" }, person.motive)));

  if (person.suspicion != null) {
    wrap.append(el("div", { className: "card sheet" },
      el("div", { className: "label" }, `Suspicion ${person.suspicion}%`),
      meter(person.suspicion, 100, person.suspicion >= 70 ? "warn" : "")));
  }

  const list = el("div", { className: "list", style: "margin-top:1rem" });
  for (const q of qs.questions) {
    list.append(el("button", {
      className: `entry ${q.asked ? "done" : ""}`,
      onclick: () => askQuestion(q.topic),
    },
      el("span", { className: "idx" }, q.asked ? "✓" : "?"),
      el("span", { className: "title" }, q.question),
      el("span", { className: "meta" }, q.asked ? "asked" : q.unlocked ? "new" : "")));
  }
  wrap.append(list);
  return wrap;
};

function askQuestion(topic) {
  const r = guard(Bridge.call("ask", { suspect_id: State.suspectId, topic }));
  if (!r) return;
  syncDashboard(r);

  const body = el("div", {},
    el("p", { className: "typed brief", style: "font-size:.95rem" }, `“${r.answer}”`));
  if (r.repeat) body.append(el("p", { className: "typed muted" }, "They have nothing to add."));

  for (const c of r.new_contradictions) {
    const block = el("div", { className: "card sheet" },
      el("div", { className: "card-head" },
        el("h3", {}, `Contradiction — ${c.topic}`),
        el("span", { className: "stamp" }, `+${c.penalty} suspicion`)),
      el("p", { className: "typed" }, `${c.suspect} says: ${c.claim}`));
    for (const other of c.contradicted_by) {
      block.append(el("p", { className: "typed" }, `${other.name} says: ${other.text}`));
    }
    body.append(block);
  }
  modal(r.suspect, body, [
    el("button", { className: "btn", onclick: () => { closeModal(); render(); } }, "Continue"),
  ]);
}

/* -------------------------------------------------------------- evidence */
views.evidence = () => {
  const data = guard(Bridge.call("evidence"));
  const wrap = el("div", {}, head("Evidence held", data ? `${data.evidence.length} items` : ""));
  if (!data) return wrap;
  if (!data.evidence.length) {
    wrap.append(el("p", { className: "typed muted" }, "You are not carrying anything yet."));
    return wrap;
  }
  const grid = el("div", { className: "grid2" });
  for (const ev of data.evidence) {
    const card = el("div", { className: "card sheet" },
      el("div", { className: "card-head" },
        el("h3", {}, ev.name),
        ev.cleared ? el("span", { className: "stamp grey" }, "Cleared") : null),
      el("p", { className: "typed", style: "margin:.35rem 0 .6rem" }, ev.description),
      el("div", { style: "display:flex;align-items:center;gap:.55rem;flex-wrap:wrap" },
        el("span", { className: `evidence-tag ${String(ev.type).toLowerCase()}` }, ev.type),
        el("span", { className: "label" }, `${ev.reliability}%`),
        el("div", { style: "flex:1;min-width:5rem" }, meter(ev.reliability, 100))));
    if (ev.comparable) {
      card.append(el("button", {
        className: "btn ghost", style: "margin-top:.7rem",
        onclick: () => openComparison(ev),
      }, "Compare against a belonging"));
    }
    grid.append(card);
  }
  wrap.append(grid);
  return wrap;
};

function openComparison(ev) {
  const t = guard(Bridge.call("targets", { evidence_id: ev.id }));
  if (!t) return;
  const list = el("div", { className: "list" });
  for (const target of t.targets) {
    list.append(el("button", {
      className: "entry",
      onclick: () => runComparison(ev.id, target),
    }, el("span", { className: "idx" }, "→"), el("span", { className: "title" }, target), el("span", {})));
  }
  modal(`Compare: ${ev.name}`,
    el("div", {},
      el("p", { className: "typed muted" },
        "A wrong match costs twelve points, so think before you work through the list."),
      list));
}

function runComparison(evidenceId, target) {
  const r = guard(Bridge.call("compare", { evidence_id: evidenceId, target }));
  if (!r) return;
  syncDashboard(r);
  const body = el("div", { className: "card sheet" },
    el("div", { className: "card-head" },
      el("h3", {}, r.verdict),
      el("span", { className: `stamp ${r.match ? "green" : "grey"}` }, `${r.confidence}%`)),
    el("p", { className: "typed" }, `${r.evidence} compared with ${r.target}.`),
    r.repeat ? el("p", { className: "typed muted" }, "You have already run this comparison.") : null);
  modal("Match analysis", body, [
    el("button", { className: "btn", onclick: () => { closeModal(); render(); } }, "Continue"),
  ]);
}

/* -------------------------------------------------------------- timeline */
views.timeline = () => {
  const data = guard(Bridge.call("timeline"));
  const wrap = el("div", {}, head("Timeline", "Established"));
  if (!data) return wrap;
  if (!data.timeline.length) {
    wrap.append(el("p", { className: "typed muted" }, "Nothing established yet."));
    return wrap;
  }
  const tl = el("div", { className: "timeline" });
  for (const e of data.timeline) {
    tl.append(el("div", { className: `ev ${e.revealed ? "revealed" : ""}` },
      el("time", {}, e.time),
      el("div", { className: "typed" }, e.text,
        e.revealed ? el("span", { className: "label", style: "margin-left:.5rem" }, "uncovered") : null)));
  }
  wrap.append(tl);
  return wrap;
};

/* -------------------------------------------------------------- notebook */
views.notebook = () => {
  const data = guard(Bridge.call("notebook"));
  const wrap = el("div", {}, head("Notebook"));
  if (!data) return wrap;

  const nb = el("div", { className: "card sheet" }, el("h3", {}, "Established"));
  if (data.confirmed.length) {
    for (const line of data.confirmed) nb.append(el("p", { className: "typed", style: "margin:.2rem 0" }, `— ${line}`));
  } else {
    nb.append(el("p", { className: "typed muted" }, "Nothing yet."));
  }
  wrap.append(nb);

  if (data.open.length) {
    const open = el("div", { className: "card sheet" }, el("h3", {}, "Still open"));
    for (const line of data.open) open.append(el("p", { className: "typed muted", style: "margin:.2rem 0" }, `? ${line}`));
    wrap.append(open);
  }

  if (data.board.length) {
    const board = el("div", { className: "card sheet" }, el("h3", {}, "Evidence board"));
    for (const entry of data.board) {
      const t = el("div", { className: "thread" });
      for (const line of entry.threads) {
        t.append(el("div", { className: `line ${line.cleared ? "cleared" : ""}` },
          el("span", {}, line.label),
          el("span", { className: "tabular" }, line.cleared ? "cleared" : `+${line.weight}`)));
      }
      board.append(el("div", { style: "margin-bottom:.7rem" },
        el("div", { className: "label" }, entry.suspect), t));
    }
    wrap.append(board);
  }

  if (data.reliability.length) {
    const rel = el("div", { className: "card sheet" }, el("h3", {}, "How much you can trust it"));
    for (const r of data.reliability) {
      rel.append(el("div", { style: "display:grid;grid-template-columns:1fr 8rem 3rem;gap:.6rem;align-items:center;padding:.16rem 0" },
        el("span", { className: "typed", style: "font-size:.82rem" }, r.name),
        meter(r.reliability, 100, r.confirmed ? "good" : ""),
        el("span", { className: "label tabular" }, `${r.reliability}%`)));
    }
    wrap.append(rel);
  }
  return wrap;
};

/* --------------------------------------------------------------- analyst */
views.analyst = () => {
  const data = guard(Bridge.call("assess"));
  const wrap = el("div", {}, head("Deduction engine", data ? data.certainty : ""));
  if (!data || !data.available) {
    wrap.append(el("p", { className: "typed muted" }, "The model is not available for this case."));
    return wrap;
  }

  wrap.append(el("div", { className: "card sheet" },
    el("p", { className: "typed", style: "margin:0" },
      `Naive Bayes and logistic regression, trained on ${data.trained_on} other cases ` +
      `covering ${data.samples} suspects. This case was excluded from training, so the ` +
      `model has never seen its answer.`),
    el("p", { className: "typed muted", style: "margin:.5rem 0 0" },
      `Evidence coverage ${data.coverage}% · Certainty: ${data.certainty}`)));

  const chart = el("div", { className: "card sheet" }, el("h3", {}, "Ranking"));
  for (const r of data.ranking) {
    chart.append(el("div", { style: "display:grid;grid-template-columns:10rem 1fr 3.4rem;gap:.7rem;align-items:center;padding:.28rem 0" },
      el("span", { style: "font-weight:700;font-size:.85rem" }, r.name),
      meter(r.share, 100, r.share > 50 ? "warn" : ""),
      el("span", { className: "label tabular" }, `${r.share}%`)));
  }
  wrap.append(chart);

  const top = data.ranking[0];
  if (top.drivers.length) {
    const why = el("div", { className: "card sheet" },
      el("h3", {}, `What drives the figure for ${top.name}`));
    for (const d of top.drivers) {
      why.append(el("div", { className: "line", style: "display:flex;justify-content:space-between;padding:.18rem 0" },
        el("span", { className: "typed", style: "font-size:.82rem" }, d.feature),
        el("span", { className: "label tabular" }, `${d.impact > 0 ? "+" : ""}${d.impact}`)));
    }
    wrap.append(why);
  }

  wrap.append(el("p", { className: "typed muted", style: "margin-top:1rem" },
    "The model reads patterns, not guilt. It has no access to the answer and it can be wrong. " +
    "Check its reasoning against your own before you accuse anyone."));
  return wrap;
};

/* ---------------------------------------------------------------- hints */
function askHint() {
  const d = State.dashboard;
  if (!d) return;
  modal("Request assistance",
    el("div", {},
      el("p", { className: "typed" }, `Hints remaining: ${d.hints_remaining}`),
      el("p", { className: "typed muted" }, "Each one costs fifty points.")),
    [el("button", {
      className: "btn",
      disabled: d.hints_remaining <= 0,
      onclick: () => {
        const r = guard(Bridge.call("hint"));
        if (!r) return;
        syncDashboard(r);
        modal("Hint", el("p", { className: "typed brief" }, r.text),
          [el("button", { className: "btn", onclick: () => { closeModal(); render(); } }, "Continue")]);
      },
    }, "Use a hint"),
     el("button", { className: "btn ghost", onclick: closeModal }, "Manage without")]);
}

/* -------------------------------------------------------------- accusing */
views.accuse = () => {
  const data = guard(Bridge.call("suspects"));
  const wrap = el("div", {}, head("Final accusation", "Closes the file"));
  if (!data) return wrap;
  wrap.append(el("p", { className: "typed brief" },
    "Naming the wrong person costs three hundred points and closes the investigation. " +
    "You can reopen the case later, but this attempt will be on your record."));
  const list = el("div", { className: "list", style: "margin-top:1rem" });
  for (const s of data.suspects) {
    list.append(el("button", {
      className: "entry",
      onclick: () => confirmAccusation(s),
    },
      el("span", { className: "idx" }, "!"),
      el("span", {},
        el("span", { className: "title" }, s.name),
        el("span", { className: "sub" }, s.motive)),
      el("span", { className: "meta" }, s.suspicion == null ? "" : `${s.suspicion}%`)));
  }
  wrap.append(list);
  return wrap;
};

function confirmAccusation(s) {
  modal(`Accuse ${s.name}?`,
    el("p", { className: "typed" },
      "This is final. The file closes either way and the result goes on your record."),
    [el("button", { className: "btn danger", onclick: () => doAccuse(s.id) }, `Accuse ${s.name}`),
     el("button", { className: "btn ghost", onclick: closeModal }, "Not yet")]);
}

function doAccuse(suspectId) {
  const r = guard(Bridge.call("accuse", { suspect_id: suspectId }));
  if (!r) return;
  closeModal();
  State.caseOpen = false;
  refreshProfile();

  const body = el("div", {});
  body.append(el("div", { style: "text-align:right;margin-bottom:.8rem" },
    el("span", { className: `stamp big land ${r.solved ? "green" : ""}` },
      r.solved ? "Case closed" : "Wrongly accused")));

  body.append(el("div", { className: "grid2" },
    stat("Culprit", r.culprit),
    stat("You accused", r.accused),
    stat("Score", `${r.score} / ${r.par}`),
    stat("Evidence", `${r.evidence_found}/${r.evidence_total}`),
    stat("Contradictions", r.contradictions),
    stat("Rating", stars(r.stars))));

  body.append(el("div", { className: "card sheet" },
    el("div", { className: "label" }, "Experience earned"),
    el("div", { style: "font-size:1.4rem;font-weight:700" }, `+${r.xp}`)));

  if (r.promoted) {
    body.append(el("div", { className: "card sheet" },
      el("h3", {}, "Promotion"),
      el("p", { className: "typed" }, `${r.previous_rank} → ${r.rank}`)));
  }

  if (r.missed && r.missed.length) {
    const missed = el("div", { className: "card sheet" }, el("h3", {}, "What you never found"));
    for (const m of r.missed) missed.append(el("p", { className: "typed" }, `— ${m}`));
    body.append(missed);
  }

  body.append(el("div", { className: "card sheet" },
    el("h3", {}, "What actually happened"),
    el("p", { className: "typed brief" }, r.solution)));

  modal(r.solved ? "Case solved" : "Wrong accusation", body, [
    el("button", { className: "btn", onclick: () => { closeModal(); go("library"); } }, "Back to the case files"),
  ]);
}

/* ------------------------------------------------------- keyboard access */
document.addEventListener("keydown", (e) => {
  if (!State.caseOpen || !$("#overlay").hidden) return;
  if (e.target.tagName === "INPUT") return;
  const map = { 1: "locations", 2: "suspects", 3: "evidence", 4: "timeline", 5: "notebook", 6: "analyst" };
  if (map[e.key]) go(map[e.key]);
  if (e.key.toLowerCase() === "h") askHint();
});

boot();

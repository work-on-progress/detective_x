"""Small helpers used by build_cases.py to keep the case data readable."""

from __future__ import annotations

import json
from pathlib import Path


def ev(eid, name, desc, etype, rel, weight=0, implicates=None, rh=False,
       cleared_by=None, requires=None, matches=None, tags=None):
    d = {
        "id": eid, "name": name, "description": desc, "type": etype,
        "reliability": rel, "weight": weight,
    }
    if implicates:
        d["implicates"] = implicates
    if rh:
        d["is_red_herring"] = True
    if cleared_by:
        d["cleared_by"] = cleared_by
    if requires:
        d["requires"] = list(requires)
    if matches:
        d["matches"] = list(matches)
    if tags:
        d["tags"] = list(tags)
    return d


def st(topic, claim, question, text, unlocked_by=None, lie=False):
    d = {"topic": topic, "claim": claim, "question": question, "text": text}
    if unlocked_by:
        d["unlocked_by"] = unlocked_by
    if lie:
        d["is_lie"] = True
    return d


def sus(sid, name, age, occupation, relation, motive, base, belongings, statements):
    return {
        "id": sid, "name": name, "age": age, "occupation": occupation,
        "relation": relation, "motive": motive, "base_suspicion": base,
        "belongings": list(belongings), "statements": list(statements),
    }


def search(sid, label, yields, flavour=""):
    return {"id": sid, "label": label, "yields": list(yields), "flavour": flavour}


def loc(lid, name, icon, description, searchables):
    return {
        "id": lid, "name": name, "icon": icon,
        "description": description, "searchables": list(searchables),
    }


def tl(time, text, hidden=False, by=None):
    d = {"time": time, "text": text}
    if hidden:
        d["hidden"] = True
        d["revealed_by"] = by
    return d


def case(cid, title, subtitle, difficulty, culprit, setting, crime, window,
         briefing, solution, topics, suspects, locations, evidence, timeline, hints):
    return {
        "schema_version": 1,
        "case_id": cid,
        "title": title,
        "subtitle": subtitle,
        "difficulty": difficulty,
        "culprit_id": culprit,
        "setting": setting,
        "crime": crime,
        "window": window,
        "briefing": briefing,
        "solution": solution,
        "topics": topics,
        "suspects": suspects,
        "locations": locations,
        "evidence": evidence,
        "timeline": timeline,
        "hints": hints,
    }


def write(cases, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for c in cases:
        path = out_dir / f"case_{c['case_id']:03d}.json"
        path.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    index = [
        {
            "id": c["case_id"],
            "title": c["title"],
            "subtitle": c["subtitle"],
            "difficulty": c["difficulty"],
            "setting": c["setting"],
            "file": f"case_{c['case_id']:03d}.json",
        }
        for c in cases
    ]
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return len(cases)

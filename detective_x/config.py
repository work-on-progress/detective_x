"""Tunable constants. Everything numeric that the game balances on lives here."""

from __future__ import annotations

from pathlib import Path

APP_NAME = "Detective X"
VERSION = "2.0.0"
SAVE_SCHEMA = 1

PACKAGE_ROOT = Path(__file__).resolve().parent
CASE_DIR = PACKAGE_ROOT / "data" / "cases"
DEFAULT_SAVE = Path("saves") / "player.json"

STARTING_SCORE = 0

SCORE_TABLE: dict[str, int] = {
    "evidence_found": 30,
    "key_evidence_found": 45,
    "contradiction_found": 50,
    "correct_comparison": 40,
    "wrong_comparison": -12,
    "timeline_revealed": 25,
    "chain_unlocked": 60,
    "hint_used": -50,
    "repeat_search": -10,
    "repeat_question": -5,
    "red_herring_cleared": 35,
    "wrong_accusation": -300,
}

CONTRADICTION_PENALTY = 20
RED_HERRING_DECAY = 0.0

# Stars are earned against the maximum attainable score for that case,
# not against a fixed number, because cases differ in size.
STAR_THRESHOLDS = [(0.92, 5), (0.78, 4), (0.60, 3), (0.40, 2), (0.0, 1)]

BASE_XP_SOLVED = 120
BASE_XP_FAILED = 25

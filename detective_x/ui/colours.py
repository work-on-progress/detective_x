"""Colour via raw escape sequences. No colour library is used."""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
AMBER = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
GREY = "\033[90m"

_enabled: bool | None = None


def supports_colour() -> bool:
    global _enabled
    if _enabled is not None:
        return _enabled
    if os.environ.get("NO_COLOR"):
        _enabled = False
    elif os.environ.get("TERM") == "dumb":
        _enabled = False
    else:
        _enabled = bool(getattr(sys.stdout, "isatty", lambda: False)())
    return _enabled


def disable() -> None:
    global _enabled
    _enabled = False


def paint(text: str, *codes: str) -> str:
    if not supports_colour() or not codes:
        return text
    return "".join(codes) + text + RESET


def heat(value: int) -> str:
    """Colour a 0-100 suspicion figure by how alarming it is."""
    if value >= 70:
        return RED
    if value >= 45:
        return AMBER
    return GREY

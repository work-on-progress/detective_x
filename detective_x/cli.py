"""Command-line options for the terminal build."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import APP_NAME, VERSION


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="detective_x",
        description=f"{APP_NAME} {VERSION} — a terminal investigation game.",
    )
    p.add_argument("--case", type=int, metavar="N", help="open a case directly by number")
    p.add_argument("--debug", action="store_true",
                   help="reveal all evidence, skip gating, fix the random seed")
    p.add_argument("--no-animation", action="store_true", help="disable loading effects")
    p.add_argument("--ascii", action="store_true", help="use ASCII borders")
    p.add_argument("--no-colour", "--no-color", dest="no_colour", action="store_true",
                   help="disable colour output")
    p.add_argument("--save", type=Path, default=Path("saves"),
                   help="directory to keep save files in (default: ./saves)")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    return p.parse_args(argv)

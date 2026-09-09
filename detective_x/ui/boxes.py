"""Terminal drawing, built by hand because no formatting library is used.

The interesting problem here is width. Python counts a character; a terminal
draws a column, and the two are not the same for wide glyphs. Every pad in
this module measures columns, not characters, and colour codes are stripped
before measuring because escape sequences occupy no columns at all.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
import unicodedata

ANSI = re.compile(r"\033\[[0-9;]*m")

STYLES = {
    "double": "╔╗╚╝═║╠╣",
    "single": "┌┐└┘─│├┤",
    "round": "╭╮╰╯─│├┤",
    "ascii": "++++-|++",
}

_FORCE_ASCII = False


def use_ascii(flag: bool = True) -> None:
    global _FORCE_ASCII
    _FORCE_ASCII = flag


def display_width(text: str) -> int:
    """Columns the terminal will use, not len()."""
    plain = ANSI.sub("", text)
    width = 0
    for ch in plain:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad(text: str, target: int) -> str:
    return text + " " * max(0, target - display_width(text))


def clip(text: str, target: int) -> str:
    if display_width(text) <= target:
        return text
    out = ""
    for ch in ANSI.sub("", text):
        if display_width(out + ch) > target - 1:
            return out + "…"
        out += ch
    return out


def terminal_width(default: int = 80, cap: int = 96) -> int:
    try:
        cols = shutil.get_terminal_size((default, 24)).columns
    except OSError:
        cols = default
    return max(40, min(cols - 2, cap))


def wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(para, width=width) or [""])
    return lines


def draw_box(
    title: str | None,
    lines: list[str],
    style: str = "double",
    width: int | None = None,
    align_title: str = "center",
) -> str:
    """Return a finished box as a string. The caller decides whether to print it."""
    if _FORCE_ASCII:
        style = "ascii"
    chars = STYLES.get(style, STYLES["double"])
    tl, tr, bl, br, h, v, ml, mr = chars

    width = width or terminal_width()
    inner = width - 4

    body: list[str] = []
    for line in lines:
        if line == "---":
            body.append("---")
        else:
            body.extend(wrap(line, inner) or [""])

    out = [tl + h * (width - 2) + tr]

    if title:
        text = clip(title, inner)
        if align_title == "center":
            space = inner - display_width(text)
            left = space // 2
            rendered = " " * left + text
        else:
            rendered = text
        out.append(f"{v} {pad(rendered, inner)} {v}")
        out.append(ml + h * (width - 2) + mr)

    for line in body:
        if line == "---":
            out.append(ml + h * (width - 2) + mr)
        else:
            out.append(f"{v} {pad(clip(line, inner), inner)} {v}")

    out.append(bl + h * (width - 2) + br)
    return "\n".join(out)


def rule(width: int | None = None, char: str = "─") -> str:
    if _FORCE_ASCII:
        char = "-"
    return char * (width or terminal_width())


def bar(value: int, total: int, width: int = 10) -> str:
    filled = round(width * value / total) if total else 0
    filled = max(0, min(width, filled))
    if _FORCE_ASCII:
        return "#" * filled + "." * (width - filled)
    return "█" * filled + "░" * (width - filled)


def stars(count: int, out_of: int = 5) -> str:
    if _FORCE_ASCII:
        return "*" * count + "-" * (out_of - count)
    return "★" * count + "☆" * (out_of - count)


def columns(pairs: list[tuple[str, str]], width: int) -> list[str]:
    label_width = max((display_width(k) for k, _ in pairs), default=0)
    return [f"{pad(k, label_width)} : {v}" for k, v in pairs]


def clear() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def enable_windows_unicode() -> None:
    if os.name == "nt":
        try:
            os.system("chcp 65001 >nul")
        except OSError:
            use_ascii(True)

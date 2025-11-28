"""Terminal helpers for optional colorized output.

Migrated from neo_rx.term to neo_core.term.
"""

from __future__ import annotations

import os
import sys
from typing import Literal

ColorLevel = Literal["ok", "warning", "error", "info"]

_ANSI = {
    "reset": "\x1b[0m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "blue": "\x1b[34m",
}


def supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _color_wrap(text: str, code: str, enabled: bool) -> str:
    if not enabled or code not in _ANSI:
        return text
    return f"{_ANSI[code]}{text}{_ANSI['reset']}"


def status_label(level: ColorLevel, *, enabled: bool = True) -> str:
    normalized = level.lower()
    if normalized == "ok":
        return _color_wrap("[OK     ]", "green", enabled)
    if normalized == "warning":
        return _color_wrap("[WARNING]", "yellow", enabled)
    if normalized == "error":
        return _color_wrap("[ERROR  ]", "red", enabled)
    return _color_wrap("[INFO   ]", "blue", enabled)


def color_text(text: str, *, color: str = "blue", enabled: bool = True) -> str:
    return _color_wrap(text, color, enabled)

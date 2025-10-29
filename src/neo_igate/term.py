"""Terminal helpers for optional colorized output.

Keep this deliberately tiny and dependency-free. Consumers should decide
when to enable colors (CLI flags or environment). The helpers respect the
NO_COLOR environment variable and whether stdout is a TTY.
"""

from __future__ import annotations

import os
import sys
from typing import Literal

ColorLevel = Literal["ok", "warning", "error", "info"]

# Simple ANSI escape sequences (widely supported). Keep codes minimal so
# logs that accidentally include them remain readable.
_ANSI = {
    "reset": "\x1b[0m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "blue": "\x1b[34m",
}


def supports_color() -> bool:
    """Return True when terminal colors are supported by default.

    Respects the NO_COLOR environment variable and checks that stdout is a
    TTY. Consumers may still force-enable or disable coloring via CLI
    flags; this helper only expresses the default auto-detection policy.
    """
    if os.getenv("NO_COLOR"):
        return False
    # When running under pytest or captured output, stdout may not be a TTY.
    return sys.stdout.isatty()


def _color_wrap(text: str, code: str, enabled: bool) -> str:
    if not enabled or code not in _ANSI:
        return text
    return f"{_ANSI[code]}{text}{_ANSI['reset']}"


def status_label(level: ColorLevel, *, enabled: bool = True) -> str:
    """Return a short status label suitable for human-readable output.

    When ``enabled`` is False the returned label contains no ANSI codes.
    """
    normalized = level.lower()
    if normalized == "ok":
        return _color_wrap("[OK     ]", "green", enabled)
    if normalized == "warning":
        return _color_wrap("[WARNING]", "yellow", enabled)
    if normalized == "error":
        return _color_wrap("[ERROR  ]", "red", enabled)
    return _color_wrap("[INFO   ]", "blue", enabled)


def color_text(text: str, *, color: str = "blue", enabled: bool = True) -> str:
    """Return ``text`` wrapped in the requested ANSI color when enabled."""
    return _color_wrap(text, color, enabled)


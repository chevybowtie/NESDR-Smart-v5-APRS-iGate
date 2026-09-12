"""Shared helpers for weekly-rotating logs and JSON-lines data files.

Long-running (months-scale) deployments need bounded on-disk growth for both
plain-text logs and the JSON-lines capture files (see HARDENING.md items
5-7). This module centralizes that rotation/retention policy, built on top
of the standard library's `TimedRotatingFileHandler` so the rollover and
pruning logic does not need to be reimplemented per call site.

Retention defaults to 12 weeks and can be overridden per call site via an
environment variable (see `resolve_retention_weeks`).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

DEFAULT_RETENTION_WEEKS = 12


def resolve_retention_weeks(env_var: str, default: int = DEFAULT_RETENTION_WEEKS) -> int:
    """Return the retention period, in weeks, configured via `env_var`.

    Falls back to `default` if the variable is unset, empty, or not a
    positive integer.
    """
    raw = os.environ.get(env_var)
    if raw:
        try:
            value = int(raw.strip())
        except ValueError:
            value = 0
        if value > 0:
            return value
    return default


def build_weekly_rotating_handler(
    path: Path, *, retention_weeks: int, delay: bool = True
) -> logging.handlers.TimedRotatingFileHandler:
    """Build a handler that rotates `path` weekly, keeping `retention_weeks` backups.

    `delay` controls whether the file is opened immediately (`False`,
    matching plain `FileHandler` semantics) or lazily on first write
    (`True`, the default here since JSON-lines writers should not create an
    empty file before there is anything to log).
    """
    return logging.handlers.TimedRotatingFileHandler(
        str(path),
        when="W0",  # roll over weekly, on Monday
        interval=1,
        backupCount=retention_weeks,
        encoding="utf-8",
        utc=True,
        delay=delay,
    )


class RotatingJsonlWriter:
    """Append lines to `path`, rotating weekly with bounded retention.

    Reuses `TimedRotatingFileHandler`'s rollover/retention logic instead of
    reimplementing it, so a JSON-lines capture file (e.g.
    `adsb_aircraft.jsonl`, `wspr_spots.jsonl`) does not grow without bound
    over months-long runs.
    """

    def __init__(self, path: Path, *, retention_env_var: str) -> None:
        self.path = Path(path)
        self.retention_weeks = resolve_retention_weeks(retention_env_var)
        self._handler = build_weekly_rotating_handler(
            self.path, retention_weeks=self.retention_weeks
        )
        self._handler.setFormatter(logging.Formatter("%(message)s"))

    def write_line(self, line: str) -> None:
        """Append a single line (without a trailing newline) to the file."""
        record = logging.LogRecord(
            name="neo_rx.rotation",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=line,
            args=None,
            exc_info=None,
        )
        self._handler.emit(record)

    def close(self) -> None:
        self._handler.close()

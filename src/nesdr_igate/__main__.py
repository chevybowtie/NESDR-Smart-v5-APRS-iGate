"""Module entry point so `python -m nesdr_igate` dispatches to the CLI."""

from __future__ import annotations

from .cli import main


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

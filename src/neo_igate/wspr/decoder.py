"""WSPR decoder wrapper (skeleton).

This module will wrap an external decoder (eg. wsprd) or a library binding
and emit parsed spots. For now it provides a lightweight stub used by the
CLI and unit tests.
"""

from __future__ import annotations

import logging
from typing import Iterable

LOG = logging.getLogger(__name__)


class WsprDecoder:
    def __init__(self, options: dict | None = None) -> None:
        self.options = options or {}

    def _parse_line(self, line: str) -> dict | None:
        """Parse a single line of (simulated) wsprd output into a spot dict.

        Expected (fixture) format:
          YYYY-MM-DD HH:MM:SS <freq_hz> <call> <grid> <snr_db> [<drift>]

        This parser is intentionally permissive to allow minor format
        differences in upstream decoder output while providing a stable
        structure for tests.
        """
        import re

        line = line.strip()
        if not line:
            return None

        pattern = re.compile(
            r"(?P<date>\d{4}-\d{2}-\d{2})\s+"
            r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
            r"(?P<freq>\d+)\s+"
            r"(?P<call>\S+)\s+"
            r"(?P<grid>\S+)\s+"
            r"(?P<snr>-?\d+)(?:\s+(?P<drift>[-+]?\d+(?:\.\d+)?))?"
        )
        m = pattern.match(line)
        if not m:
            LOG.debug("Unrecognized wsprd line: %s", line)
            return None

        gd = m.groupdict()
        ts = f"{gd['date']}T{gd['time']}Z"
        try:
            freq_hz = int(gd["freq"])
        except (TypeError, ValueError):
            freq_hz = 0

        spot = {
            "timestamp": ts,
            "freq_hz": freq_hz,
            "call": gd.get("call"),
            "grid": gd.get("grid"),
            "snr_db": int(gd.get("snr")) if gd.get("snr") is not None else None,
            "drift": float(gd.get("drift")) if gd.get("drift") else None,
        }
        return spot

    def decode_stream(self, line_iter: Iterable[bytes | str]) -> Iterable[dict]:
        """Consume an iterable of bytes/strings (decoder stdout) and yield spot dicts.

        For production we will run `wsprd` as a subprocess and feed its
        stdout lines into this method; for unit tests we accept fixture
        lines.
        """
        for chunk in line_iter:
            if isinstance(chunk, bytes):
                try:
                    text = chunk.decode("utf-8", errors="replace")
                except Exception:
                    text = str(chunk)
            else:
                text = str(chunk)

            for raw_line in text.splitlines():
                parsed = self._parse_line(raw_line)
                if parsed is not None:
                    yield parsed

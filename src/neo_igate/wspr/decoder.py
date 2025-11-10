"""WSPR decoder wrapper (skeleton).

This module will wrap an external decoder (eg. wsprd) or a library binding
and emit parsed spots. For now it provides a lightweight stub used by the
CLI and unit tests.
"""

from __future__ import annotations

import logging
from typing import Iterable
from typing import Iterator, List

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
            "snr_db": int(gd["snr"]),
            "drift": float(gd["drift"]) if gd.get("drift") else None,
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

    def run_wsprd_subprocess(self, iq_data: bytes, band_hz: int, cmd: List[str] | None = None) -> Iterator[dict]:
        """Run `wsprd` as a subprocess, feed IQ data to stdin, and yield parsed spots.

        This function feeds the provided IQ data (as bytes) to `wsprd`'s stdin,
        runs the subprocess, and parses stdout for spots.

        If the command is not found or the subprocess cannot be started, it logs
        and returns without raising.

        Args:
            iq_data: IQ samples as bytes (int16 little-endian).
            band_hz: The band frequency in Hz.
            cmd: Optional command list; defaults to ['wsprd', '-f', str(band_hz / 1e6)].
        """
        import subprocess
        import io

        if cmd is None:
            cmd = ["wsprd", "-f", str(band_hz / 1e6)]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,  # Unbuffered
            )
        except FileNotFoundError:
            LOG.warning("wsprd binary not found: %s", cmd[0])
            return
        except Exception:
            LOG.exception("Failed to start wsprd subprocess: %s", cmd)
            return

        assert proc.stdin is not None
        assert proc.stdout is not None
        try:
            # Write IQ data to stdin
            proc.stdin.write(iq_data)
            proc.stdin.close()

            # Read stdout as text
            for line in io.TextIOWrapper(proc.stdout, encoding='utf-8', errors='replace'):
                parsed = self._parse_line(line)
                if parsed is not None:
                    yield parsed
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

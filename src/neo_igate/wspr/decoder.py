"""WSPR decoder wrapper (skeleton).

This module will wrap an external decoder (eg. wsprd) or a library binding
and emit parsed spots. For now it provides a lightweight stub used by the
CLI and unit tests.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Iterable
from typing import Iterator, List

LOG = logging.getLogger(__name__)


class WsprDecoder:
    def __init__(self, options: dict | None = None) -> None:
        self.options = options or {}
        self.wsprd_path = self._find_wsprd()

    def _find_wsprd(self) -> str | None:
        """Find the wsprd binary, preferring bundled over system."""
        # Check bundled
        bundled = os.path.join(os.path.dirname(__file__), 'bin', 'wsprd')
        if os.path.exists(bundled):
            return bundled
        # Check system
        system = shutil.which('wsprd')
        if system:
            return system
        return None

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

    def run_wsprd_subprocess(self, iq_data: bytes, band_hz: int, cmd: List[str] | None = None, keep_temp: bool = False) -> Iterator[dict]:
        """Run `wsprd` as a subprocess, feed IQ data via temp file, and yield parsed spots.

        This function writes the provided IQ data to a temporary file, runs `wsprd`
        on it, and parses stdout for spots.

        If the command is not found or the subprocess cannot be started, it logs
        and returns without raising.

        Args:
            iq_data: IQ samples as bytes (int16 little-endian).
            band_hz: The band frequency in Hz.
            cmd: Optional command list; defaults to [wsprd_path, '-f', str(band_hz / 1e6), temp_file].
        """
        if self.wsprd_path is None:
            LOG.warning("wsprd binary not found")
            return

        # Create temp directory for wsprd output files. Optionally preserve it for debugging.
        temp_dir_ctx = None
        if keep_temp:
            temp_dir = tempfile.mkdtemp()
        else:
            temp_dir_ctx = tempfile.TemporaryDirectory()
            temp_dir = temp_dir_ctx.name

        # Create temp file for IQ data
        with tempfile.NamedTemporaryFile(delete=False, suffix='.c2', dir=temp_dir) as temp_file:
            temp_file.write(iq_data)
            temp_file_path = temp_file.name

        try:
            if cmd is None:
                cmd = [self.wsprd_path, '-a', temp_dir, '-f', str(band_hz / 1e6), temp_file_path]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,  # Unbuffered
            )

            LOG.debug("Started wsprd: %s", cmd)
            LOG.debug("wsprd temp file: %s", temp_file_path)
            try:
                file_size = os.path.getsize(temp_file_path)
                samples = file_size // 4
                inferred_secs = samples / 1_200_000.0
                LOG.info("wsprd input file %s size=%d bytes -> %d complex samples (%.2f s @1.2e6)", temp_file_path, file_size, samples, inferred_secs)
                if inferred_secs < 100:
                    LOG.warning("wsprd input duration seems short (%.2fs). wsprd expects ~119s input for WSPR; this may explain missing decodes.", inferred_secs)
            except Exception:
                LOG.debug("Could not stat wsprd temp file for diagnostics")

            # Start a background thread to capture and log stderr from wsprd
            import threading

            def _log_stderr(pipe):
                try:
                    if pipe is None:
                        return
                    for sline in io.TextIOWrapper(pipe, encoding='utf-8', errors='replace'):
                        sline = sline.rstrip("\n")
                        if sline:
                            LOG.debug("wsprd[stderr]: %s", sline)
                except Exception:
                    LOG.exception("Error reading wsprd stderr")

            stderr_thread = threading.Thread(target=_log_stderr, args=(proc.stderr,), daemon=True)
            stderr_thread.start()

            assert proc.stdout is not None
            try:
                # Read stdout as text and parse lines for spots
                for line in io.TextIOWrapper(proc.stdout, encoding='utf-8', errors='replace'):
                    parsed = self._parse_line(line)
                    if parsed is not None:
                        yield parsed
            finally:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    stderr_thread.join(timeout=0.2)
                except Exception:
                    pass
        finally:
            # Clean up temp directory unless user requested to keep it for debugging
            if keep_temp:
                LOG.info("Preserved wsprd temp dir for debugging: %s", temp_dir)
            else:
                try:
                    if temp_dir_ctx is not None:
                        temp_dir_ctx.cleanup()
                    else:
                        # fallback: remove dir if exists
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    LOG.exception("Failed to cleanup wsprd temp dir: %s", temp_dir)

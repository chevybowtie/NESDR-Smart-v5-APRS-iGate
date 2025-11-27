"""Minimal APRS-IS client for uploading packets.

Migrated from neo_rx.aprs.aprsis_client.
"""
from __future__ import annotations
import io
import socket
import time
from dataclasses import dataclass
from typing import Callable, Optional
import logging

try:
    from neo_rx import __version__
except ImportError:
    __version__ = "0.2.2"

class APRSISClientError(RuntimeError):
    pass

@dataclass(slots=True)
class APRSISConfig:
    host: str
    port: int
    callsign: str
    passcode: str
    software_name: str = "neo-rx"
    software_version: str = __version__
    filter_string: str | None = None
    timeout: float = 5.0

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class RetryBackoff:
    def __init__(self, *, base_delay: float = 2.0, max_delay: float = 120.0, multiplier: float = 2.0, clock: Optional[Callable[[], float]] = None) -> None:
        if base_delay <= 0:
            raise ValueError("base_delay must be positive")
        if max_delay < base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if multiplier < 1.0:
            raise ValueError("multiplier must be >= 1.0")
        self._base = base_delay
        self._max = max_delay
        self._multiplier = multiplier
        self._clock = clock or time.monotonic
        self._current = base_delay
        self._next_attempt = 0.0

    @property
    def current_delay(self) -> float:
        return self._current

    def ready(self) -> bool:
        return self._clock() >= self._next_attempt

    def record_failure(self) -> float:
        delay = self._current
        self._next_attempt = self._clock() + delay
        self._current = min(self._current * self._multiplier, self._max)
        return delay

    def record_success(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._current = self._base
        self._next_attempt = 0.0

class APRSISClient:
    def __init__(self, config: APRSISConfig) -> None:
        self._config = config
        self._socket: Optional[socket.socket] = None
        self._reader: Optional[io.BufferedReader] = None
        self._writer: Optional[io.BufferedWriter] = None

    def connect(self) -> None:
        if self._socket is not None:
            logger.debug("APRS-IS session already active for %s:%s", self._config.host, self._config.port)
            return
        logger.debug("Opening APRS-IS session to %s:%s as %s", self._config.host, self._config.port, self._config.callsign)
        try:
            sock = socket.create_connection((self._config.host, self._config.port), timeout=self._config.timeout)
        except OSError as exc:
            raise APRSISClientError(f"Unable to connect to APRS-IS server {self._config.host}:{self._config.port}: {exc}") from exc
        sock.settimeout(self._config.timeout)
        self._socket = sock
        self._reader = sock.makefile("rb")
        self._writer = sock.makefile("wb")
        try:
            login = self._build_login_line().encode("ascii") + b"\n"
            writer = self._require_writer()
            writer.write(login)
            writer.flush()
            self._await_logresp()
            logger.info("Connected to APRS-IS %s:%s as %s", self._config.host, self._config.port, self._config.callsign)
        except Exception:
            self.close()
            raise

    def send_packet(self, packet: str | bytes) -> None:
        writer = self._require_writer()
        packet_bytes = packet.encode("ascii", errors="replace") if isinstance(packet, str) else bytes(packet)
        packet_bytes = packet_bytes.rstrip(b"\r\n") + b"\n"
        try:
            writer.write(packet_bytes)
            writer.flush()
        except OSError as exc:
            raise APRSISClientError(f"Failed to send packet to APRS-IS: {exc}") from exc

    def close(self) -> None:
        had = any(c is not None for c in (self._writer, self._reader, self._socket))
        if self._writer is not None:
            try: self._writer.close()
            except OSError: pass
            self._writer = None
        if self._reader is not None:
            try: self._reader.close()
            except OSError: pass
            self._reader = None
        if self._socket is not None:
            try: self._socket.close()
            except OSError: pass
            self._socket = None
        if had:
            logger.info("Closed APRS-IS connection to %s:%s", self._config.host, self._config.port)
        else:
            logger.debug("APRS-IS close requested with no active session for %s:%s", self._config.host, self._config.port)

    def __enter__(self) -> "APRSISClient":
        self.connect(); return self
    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _await_logresp(self) -> None:
        reader = self._require_reader()
        for _ in range(5):
            try:
                line = reader.readline()
            except OSError as exc:
                raise APRSISClientError(f"Error reading APRS-IS response: {exc}") from exc
            if not line:
                raise APRSISClientError("APRS-IS server closed connection during login")
            decoded = line.decode("utf-8", errors="replace").strip().lower()
            if decoded.startswith("# logresp"):
                if any(term in decoded for term in ("unverified", "invalid", "reject", "bad")):
                    raise APRSISClientError(f"APRS-IS login failed: {decoded}")
                if "verified" in decoded or " ok" in decoded:
                    return
        raise APRSISClientError("APRS-IS login response not received")

    def _build_login_line(self) -> str:
        base = f"user {self._config.callsign} pass {self._config.passcode} vers {self._config.software_name} {self._config.software_version}"
        if self._config.filter_string:
            base += f" filter {self._config.filter_string}"
        return base

    def _require_reader(self) -> io.BufferedReader:
        if self._reader is None:
            raise APRSISClientError("APRS-IS connection not established")
        return self._reader

    def _require_writer(self) -> io.BufferedWriter:
        if self._writer is None:
            raise APRSISClientError("APRS-IS connection not established")
        return self._writer

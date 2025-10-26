"""Minimal APRS-IS client for uploading packets."""

from __future__ import annotations

import io
import socket
from dataclasses import dataclass
from typing import Optional


class APRSISClientError(RuntimeError):
    """Raised when APRS-IS connection or transmission fails."""


@dataclass(slots=True)
class APRSISConfig:
    """Connection parameters and metadata for APRS-IS sessions."""

    host: str
    port: int
    callsign: str
    passcode: str
    software_name: str = "nesdr-igate"
    software_version: str = "0.0.0"
    filter_string: str | None = None
    timeout: float = 5.0


class APRSISClient:
    """Manage APRS-IS connectivity for uploading APRS packets."""

    def __init__(self, config: APRSISConfig) -> None:
        """Initialise the client with the desired APRS-IS configuration."""
        self._config = config
        self._socket: Optional[socket.socket] = None
        self._reader: Optional[io.BufferedReader] = None
        self._writer: Optional[io.BufferedWriter] = None

    def connect(self) -> None:
        """Establish the APRS-IS session, returning immediately if already connected."""
        if self._socket is not None:
            return
        try:
            sock = socket.create_connection(
                (self._config.host, self._config.port), timeout=self._config.timeout
            )
        except OSError as exc:
            raise APRSISClientError(
                f"Unable to connect to APRS-IS server {self._config.host}:{self._config.port}: {exc}"
            ) from exc

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
        except Exception:
            # Ensure partially established sockets are released on failure.
            self.close()
            raise

    def send_packet(self, packet: str) -> None:
        """Transmit an already encoded TNC2 packet line to APRS-IS."""
        writer = self._require_writer()
        line = packet.rstrip("\r\n") + "\n"
        try:
            writer.write(line.encode("utf-8", errors="replace"))
            writer.flush()
        except OSError as exc:
            raise APRSISClientError(f"Failed to send packet to APRS-IS: {exc}") from exc

    def close(self) -> None:
        """Release all socket resources associated with the APRS-IS session."""
        if self._writer is not None:
            try:
                self._writer.close()
            except OSError:
                pass
            self._writer = None
        if self._reader is not None:
            try:
                self._reader.close()
            except OSError:
                pass
            self._reader = None
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def __enter__(self) -> "APRSISClient":
        """Open the connection when used as a context manager."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Ensure the connection is closed when leaving a context manager."""
        self.close()

    def _await_logresp(self) -> None:
        """Read initial server banner lines until a login response is received."""
        reader = self._require_reader()
        for _ in range(5):
            try:
                line = reader.readline()
            except OSError as exc:
                raise APRSISClientError(
                    f"Error reading APRS-IS response: {exc}"
                ) from exc
            if not line:
                raise APRSISClientError("APRS-IS server closed connection during login")
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded.startswith("# logresp"):
                normalized = decoded.lower()
                if any(
                    term in normalized
                    for term in ("unverified", "invalid", "reject", "bad")
                ):
                    raise APRSISClientError(f"APRS-IS login failed: {decoded}")
                if "verified" in normalized or " ok" in normalized:
                    return
        raise APRSISClientError("APRS-IS login response not received")

    def _build_login_line(self) -> str:
        """Compose the APRS-IS login command string."""
        base = f"user {self._config.callsign} pass {self._config.passcode} vers {self._config.software_name} {self._config.software_version}"
        if self._config.filter_string:
            base += f" filter {self._config.filter_string}"
        return base

    def _require_reader(self) -> io.BufferedReader:
        """Return the socket reader, raising if the client is disconnected."""
        if self._reader is None:
            raise APRSISClientError("APRS-IS connection not established")
        return self._reader

    def _require_writer(self) -> io.BufferedWriter:
        """Return the socket writer, raising if the client is disconnected."""
        if self._writer is None:
            raise APRSISClientError("APRS-IS connection not established")
        return self._writer

"""Minimal KISS TCP client for connecting to Direwolf.

Migrated from neo_rx.aprs.kiss_client.
"""

from __future__ import annotations
import socket
from collections.abc import ByteString
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD


class KISSCommand(IntEnum):
    DATA = 0x00
    TX_DELAY = 0x01
    PERSISTENCE = 0x02
    SLOT_TIME = 0x03
    TX_TAIL = 0x04
    FULL_DUPLEX = 0x05
    SET_HARDWARE = 0x06
    RETURN = 0x0F


class KISSClientError(RuntimeError):
    pass


@dataclass(slots=True)
class KISSClientConfig:
    host: str = "127.0.0.1"
    port: int = 8001
    timeout: float = 2.0


@dataclass(slots=True)
class KISSFrame:
    port: int
    command: KISSCommand
    payload: bytes


class KISSClient:
    def __init__(self, config: KISSClientConfig | None = None) -> None:
        self._config = config or KISSClientConfig()
        self._socket: socket.socket | None = None
        self._buffer = bytearray()

    @property
    def is_connected(self) -> bool:
        return self._socket is not None

    def connect(self) -> None:
        if self._socket is not None:
            return
        try:
            sock = socket.create_connection(
                (self._config.host, self._config.port), timeout=self._config.timeout
            )
        except OSError as exc:
            raise KISSClientError(
                f"Unable to connect to KISS server at {self._config.host}:{self._config.port}: {exc}"
            ) from exc
        sock.settimeout(self._config.timeout)
        self._socket = sock
        self._buffer.clear()

    def read_frame(self, timeout: Optional[float] = None) -> KISSFrame:
        sock = self._require_socket()
        sock.settimeout(timeout if timeout is not None else self._config.timeout)
        while True:
            frame = self._extract_frame()
            if frame is not None:
                return frame
            try:
                chunk = sock.recv(4096)
            except socket.timeout as exc:
                raise TimeoutError("Timed out waiting for KISS frame") from exc
            except OSError as exc:
                raise KISSClientError(
                    f"Socket error while reading frame: {exc}"
                ) from exc
            if not chunk:
                raise KISSClientError("KISS connection closed by remote host")
            self._buffer.extend(chunk)

    def send_frame(
        self,
        payload: ByteString,
        *,
        port: int = 0,
        command: KISSCommand | int = KISSCommand.DATA,
    ) -> None:
        sock = self._require_socket()
        payload_bytes = bytes(payload)
        command_value = int(KISSCommand(command))
        frame = bytearray()
        frame.append(FEND)
        frame.append(((command_value & 0x0F) << 4) | (port & 0x0F))
        frame.extend(_kiss_escape(payload_bytes))
        frame.append(FEND)
        try:
            sock.sendall(frame)
        except OSError as exc:
            raise KISSClientError(f"Failed to send KISS frame: {exc}") from exc

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None
            self._buffer.clear()

    def __enter__(self) -> "KISSClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _extract_frame(self) -> KISSFrame | None:
        start = self._buffer.find(FEND)
        if start == -1:
            self._buffer.clear()
            return None
        if start > 0:
            del self._buffer[:start]
        end = self._buffer.find(FEND, 1)
        if end == -1:
            return None
        frame_bytes = bytes(self._buffer[1:end])
        del self._buffer[: end + 1]
        if not frame_bytes:
            return None
        header = frame_bytes[0]
        port = header & 0x0F
        command_value = (header & 0xF0) >> 4
        command = KISSCommand(command_value)
        payload = _kiss_unescape(frame_bytes[1:])
        return KISSFrame(port=port, command=command, payload=payload)

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise KISSClientError("KISS connection not established")
        return self._socket


def _kiss_escape(payload: ByteString) -> bytes:
    """Escape a payload per the KISS protocol rules."""
    escaped = bytearray()
    for value in bytes(payload):
        if value == FEND:
            escaped.extend((FESC, TFEND))
        elif value == FESC:
            escaped.extend((FESC, TFESC))
        else:
            escaped.append(value)
    return bytes(escaped)


def _kiss_unescape(payload: bytes) -> bytes:
    """Reverse KISS-specific escape sequences within a payload."""
    decoded = bytearray()
    iterator = iter(payload)
    for value in iterator:
        if value == FESC:
            try:
                nxt = next(iterator)
            except StopIteration as exc:  # pragma: no cover - defensive
                raise KISSClientError("Truncated KISS escape sequence") from exc
            if nxt == TFEND:
                decoded.append(FEND)
            elif nxt == TFESC:
                decoded.append(FESC)
            else:  # pragma: no cover - protocol violation
                raise KISSClientError(f"Invalid KISS escape byte: {nxt:#x}")
        else:
            decoded.append(value)
    return bytes(decoded)

from __future__ import annotations

import logging

import pytest

from neo_aprs.aprs.aprsis_client import (
    APRSISClient,
    APRSISClientError,
    APRSISConfig,
    RetryBackoff,
)


def _config(**overrides: object) -> APRSISConfig:
    values: dict[str, object] = {
        "host": "aprs.example",
        "port": 14580,
        "callsign": "N0CALL",
        "passcode": "12345",
    }
    values.update(overrides)
    return APRSISConfig(**values)  # type: ignore[arg-type]


class _FakeReader:
    def __init__(self, lines: list[bytes] | None = None, error: OSError | None = None):
        self.lines = iter(lines or [])
        self.error = error
        self.closed = False

    def readline(self) -> bytes:
        if self.error is not None:
            raise self.error
        return next(self.lines, b"")

    def close(self) -> None:
        self.closed = True


class _FakeWriter:
    def __init__(self, error: OSError | None = None):
        self.writes: list[bytes] = []
        self.error = error
        self.closed = False

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        if self.error is not None:
            raise self.error

    def close(self) -> None:
        self.closed = True


class _FakeSocket:
    def __init__(self, reader: _FakeReader, writer: _FakeWriter):
        self.reader = reader
        self.writer = writer
        self.timeout: float | None = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def makefile(self, mode: str):
        return self.reader if "r" in mode else self.writer

    def close(self) -> None:
        self.closed = True


def test_connect_builds_login_with_filter_and_send_normalizes_packet(monkeypatch) -> None:
    reader = _FakeReader([b"# banner\n", b"# logresp N0CALL verified\n"])
    writer = _FakeWriter()
    sock = _FakeSocket(reader, writer)
    monkeypatch.setattr(
        "neo_aprs.aprs.aprsis_client.socket.create_connection",
        lambda address, timeout: sock,
    )

    client = APRSISClient(_config(filter_string="r/39/-96/25", timeout=3.0))
    with client:
        client.send_packet("N0CALL>APRS:test\r\n")

    assert sock.timeout == 3.0
    assert writer.writes == [
        b"user N0CALL pass 12345 vers neo-rx "
        + APRSISConfig.__dataclass_fields__["software_version"].default.encode()
        + b" filter r/39/-96/25\n",
        b"N0CALL>APRS:test\n",
    ]
    assert client._socket is None  # type: ignore[attr-defined]


@pytest.mark.parametrize("response", [b"# logresp N0CALL unverified\n", b"# logresp N0CALL invalid\n", b"# logresp N0CALL reject\n", b"# logresp N0CALL bad\n"])
def test_connect_rejects_failed_login_and_cleans_up(monkeypatch, response: bytes) -> None:
    reader = _FakeReader([response])
    writer = _FakeWriter()
    sock = _FakeSocket(reader, writer)
    monkeypatch.setattr(
        "neo_aprs.aprs.aprsis_client.socket.create_connection",
        lambda *_args, **_kwargs: sock,
    )

    client = APRSISClient(_config())
    with pytest.raises(APRSISClientError, match="login failed"):
        client.connect()

    assert sock.closed is True
    assert client._reader is None  # type: ignore[attr-defined]
    assert client._writer is None  # type: ignore[attr-defined]


def test_connect_wraps_socket_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "neo_aprs.aprs.aprsis_client.socket.create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("refused")),
    )

    with pytest.raises(APRSISClientError, match="Unable to connect"):
        APRSISClient(_config()).connect()


@pytest.mark.parametrize(
    ("reader", "message"),
    [
        (_FakeReader(error=OSError("read failed")), "Error reading"),
        (_FakeReader([]), "server closed"),
        (_FakeReader([b"# banner\n"] * 5), "not received"),
    ],
)
def test_login_response_errors(reader: _FakeReader, message: str) -> None:
    client = APRSISClient(_config())
    client._reader = reader  # type: ignore[attr-defined]

    with pytest.raises(APRSISClientError, match=message):
        client._await_logresp()


def test_send_packet_preserves_bytes_and_requires_connection() -> None:
    client = APRSISClient(_config())
    with pytest.raises(APRSISClientError, match="not established"):
        client.send_packet("N0CALL>APRS:test")

    writer = _FakeWriter()
    client._writer = writer  # type: ignore[attr-defined]
    client.send_packet(b"N0CALL>APRS:\xff\r\n")
    assert writer.writes == [b"N0CALL>APRS:\xff\n"]


def test_send_packet_wraps_writer_errors() -> None:
    client = APRSISClient(_config())
    client._writer = _FakeWriter(error=OSError("broken pipe"))  # type: ignore[attr-defined]

    with pytest.raises(APRSISClientError, match="Failed to send"):
        client.send_packet("N0CALL>APRS:test")


def test_close_handles_resources_and_is_idempotent(caplog) -> None:
    client = APRSISClient(_config())
    client._writer = _FakeWriter()  # type: ignore[attr-defined]
    client._reader = _FakeReader()  # type: ignore[attr-defined]
    client._socket = _FakeSocket(client._reader, client._writer)  # type: ignore[attr-defined]

    caplog.set_level(logging.DEBUG, logger="neo_aprs.aprs.aprsis_client")
    client.close()
    client.close()

    assert client._writer is None  # type: ignore[attr-defined]
    assert client._reader is None  # type: ignore[attr-defined]
    assert client._socket is None  # type: ignore[attr-defined]
    assert "Closed APRS-IS connection" in caplog.text
    assert "no active session" in caplog.text


def test_login_line_without_filter_and_context_manager(monkeypatch) -> None:
    reader = _FakeReader([b"# logresp N0CALL verified\n"])
    writer = _FakeWriter()
    sock = _FakeSocket(reader, writer)
    monkeypatch.setattr(
        "neo_aprs.aprs.aprsis_client.socket.create_connection",
        lambda *_args, **_kwargs: sock,
    )

    client = APRSISClient(_config())
    assert client._build_login_line() == (
        f"user N0CALL pass 12345 vers neo-rx {client._config.software_version}"
    )
    with client as connected:
        assert connected is client


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_delay": 0},
        {"base_delay": 2, "max_delay": 1},
        {"multiplier": 0.5},
    ],
)
def test_retry_backoff_rejects_invalid_configuration(kwargs) -> None:
    with pytest.raises(ValueError):
        RetryBackoff(**kwargs)


def test_retry_backoff_caps_and_resets() -> None:
    now = [0.0]
    backoff = RetryBackoff(
        base_delay=2.0,
        max_delay=5.0,
        multiplier=3.0,
        clock=lambda: now[0],
    )

    assert backoff.ready() is True
    assert backoff.record_failure() == 2.0
    assert backoff.current_delay == 5.0
    now[0] = 1.0
    assert backoff.ready() is False
    now[0] = 2.0
    assert backoff.ready() is True
    assert backoff.record_failure() == 5.0
    assert backoff.current_delay == 5.0
    backoff.reset()
    assert backoff.current_delay == 2.0
    assert backoff.ready() is True

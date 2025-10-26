"""Tests for APRS-IS client."""

from __future__ import annotations

import queue
import socket
import threading
import time

import pytest

from nesdr_igate.aprs.aprsis_client import (  # type: ignore[import]
    APRSISClient,
    APRSISClientError,
    APRSISConfig,
)


def _start_server(responder) -> tuple[int, threading.Thread]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _run() -> None:
        conn, _ = server.accept()
        try:
            responder(conn)
        finally:
            conn.close()
            server.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return port, thread


def test_aprsis_client_connect_and_send() -> None:
    login_queue: "queue.Queue[str]" = queue.Queue()
    packet_queue: "queue.Queue[str]" = queue.Queue()

    def responder(conn: socket.socket) -> None:
        conn.sendall(b"# aprsc 2.1 test\n")
        data = conn.recv(1024)
        login_queue.put(data.decode().strip())
        conn.sendall(b"# logresp TEST verified\n")
        packet = conn.recv(1024)
        packet_queue.put(packet.decode().strip())

    port, thread = _start_server(responder)

    client = APRSISClient(
        APRSISConfig(
            host="127.0.0.1",
            port=port,
            callsign="TEST",
            passcode="12345",
            software_name="tester",
            software_version="1.0",
        )
    )

    with client:
        client.send_packet("TEST>APRS:hello world")

    thread.join(timeout=1)

    assert login_queue.get(timeout=0.5) == "user TEST pass 12345 vers tester 1.0"
    assert packet_queue.get(timeout=0.5) == "TEST>APRS:hello world"


def test_aprsis_client_login_failure() -> None:
    def responder(conn: socket.socket) -> None:
        conn.sendall(b"# aprsc 2.1 test\n")
        conn.recv(1024)
        conn.sendall(b"# logresp TEST unverified\n")
        time.sleep(0.1)

    port, thread = _start_server(responder)

    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=port, callsign="TEST", passcode="12345"))

    with pytest.raises(APRSISClientError):
        client.connect()

    assert client._socket is None  # type: ignore[attr-defined]
    assert client._reader is None  # type: ignore[attr-defined]
    assert client._writer is None  # type: ignore[attr-defined]

    thread.join(timeout=1)


def test_aprsis_client_connect_failure(monkeypatch) -> None:
    def fake_create_connection(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("boom")

    monkeypatch.setattr("nesdr_igate.aprs.aprsis_client.socket.create_connection", fake_create_connection)

    client = APRSISClient(APRSISConfig(host="invalid", port=1, callsign="TEST", passcode="12345"))

    with pytest.raises(APRSISClientError) as excinfo:
        client.connect()

    assert "Unable to connect" in str(excinfo.value)


def test_aprsis_client_connect_idempotent() -> None:
    def responder(conn: socket.socket) -> None:
        conn.sendall(b"# aprsc 2.1 test\n")
        conn.recv(1024)
        conn.sendall(b"# logresp TEST verified\n")
        time.sleep(0.1)

    port, thread = _start_server(responder)

    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=port, callsign="TEST", passcode="12345"))
    client.connect()
    client.connect()
    client.close()

    thread.join(timeout=1)


def test_aprsis_client_login_connection_closed() -> None:
    def responder(conn: socket.socket) -> None:
        # Immediately close without responding
        return None

    port, thread = _start_server(responder)

    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=port, callsign="TEST", passcode="12345"))

    with pytest.raises(APRSISClientError) as excinfo:
        client.connect()

    assert "Error reading APRS-IS response" in str(excinfo.value)
    assert client._socket is None  # type: ignore[attr-defined]
    assert client._reader is None  # type: ignore[attr-defined]
    assert client._writer is None  # type: ignore[attr-defined]
    thread.join(timeout=1)


def test_aprsis_client_login_response_missing() -> None:
    def responder(conn: socket.socket) -> None:
        conn.sendall(b"# aprsc 2.1 test\n")
        conn.recv(1024)
        for _ in range(5):
            conn.sendall(b"# still waiting\n")
        time.sleep(0.1)

    port, thread = _start_server(responder)

    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=port, callsign="TEST", passcode="12345"))

    with pytest.raises(APRSISClientError) as excinfo:
        client.connect()

    assert "not received" in str(excinfo.value)
    assert client._socket is None  # type: ignore[attr-defined]
    assert client._reader is None  # type: ignore[attr-defined]
    assert client._writer is None  # type: ignore[attr-defined]
    thread.join(timeout=1)


def test_aprsis_client_send_without_connection() -> None:
    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=1, callsign="TEST", passcode="12345"))

    with pytest.raises(APRSISClientError):
        client.send_packet("TEST>APRS:hi")


def test_aprsis_client_send_flush_error() -> None:
    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=1, callsign="TEST", passcode="12345"))

    class FailingWriter:
        def write(self, data: bytes) -> int:
            self.data = data
            return len(data)

        def flush(self) -> None:
            raise OSError("flush failed")

        def close(self) -> None:  # pragma: no cover - not used in test
            pass

    client._writer = FailingWriter()  # type: ignore[attr-defined]

    with pytest.raises(APRSISClientError) as excinfo:
        client.send_packet("TEST>APRS:data")

    assert "Failed to send" in str(excinfo.value)


def test_aprsis_client_require_reader_without_connection() -> None:
    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=1, callsign="TEST", passcode="12345"))

    with pytest.raises(APRSISClientError):
        client._await_logresp()


def test_aprsis_client_close_ignores_errors() -> None:
    client = APRSISClient(APRSISConfig(host="127.0.0.1", port=1, callsign="TEST", passcode="12345"))

    class FailingCloser:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True
            raise OSError("boom")

    writer = FailingCloser()
    reader = FailingCloser()
    sock = FailingCloser()

    client._writer = writer  # type: ignore[attr-defined]
    client._reader = reader  # type: ignore[attr-defined]
    client._socket = sock  # type: ignore[attr-defined]

    client.close()

    assert client._writer is None  # type: ignore[attr-defined]
    assert client._reader is None  # type: ignore[attr-defined]
    assert client._socket is None  # type: ignore[attr-defined]
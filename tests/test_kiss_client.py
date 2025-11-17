"""Tests for the KISS TCP client implementation."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from neo_rx.aprs.kiss_client import (
    FEND,
    FESC,
    KISSClient,
    KISSClientConfig,
    KISSClientError,
    KISSCommand,
    _kiss_escape,
    _kiss_unescape,
)


def _start_kiss_server(payloads: list[bytes] | None) -> tuple[int, threading.Thread]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _run() -> None:
        conn, _ = server.accept()
        try:
            if payloads is not None:
                for payload in payloads:
                    conn.sendall(payload)
                    time.sleep(0.05)
                # Give client a moment before closing
                time.sleep(0.1)
            else:
                time.sleep(0.5)
        finally:
            conn.close()
            server.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return port, thread


def _make_frame(port: int, payload: bytes) -> bytes:
    header = bytes([(port & 0x0F)])
    body = _kiss_escape(payload)
    return bytes([FEND]) + header + body + bytes([FEND])


def test_kiss_client_receives_frame() -> None:
    frame_payload = b"test aprs"
    frame = _make_frame(0x02, frame_payload)
    port, thread = _start_kiss_server([frame])

    client = KISSClient(KISSClientConfig(host="127.0.0.1", port=port, timeout=1.0))
    with client:
        received = client.read_frame()

    thread.join(timeout=1)
    assert received.port == 0x02
    assert received.command is KISSCommand.DATA
    assert received.payload == frame_payload


def test_kiss_client_timeout() -> None:
    port, thread = _start_kiss_server(None)
    client = KISSClient(KISSClientConfig(host="127.0.0.1", port=port, timeout=0.2))
    with client:
        with pytest.raises(TimeoutError):
            client.read_frame(timeout=0.2)

    thread.join(timeout=1)


def test_kiss_client_send_frame() -> None:
    received_chunks: list[bytes] = []
    server_ready = threading.Event()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _run_server() -> None:
        server_ready.set()
        conn, _ = server.accept()
        try:
            data = conn.recv(1024)
            if data:
                received_chunks.append(data)
        finally:
            conn.close()
            server.close()

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    server_ready.wait(timeout=1)

    payload = bytes([0xC0, 0xDB, 0x11])
    client = KISSClient(KISSClientConfig(host="127.0.0.1", port=port, timeout=1.0))

    with client:
        client.send_frame(payload, port=3)

    thread.join(timeout=1)
    assert received_chunks
    sent = received_chunks[0]
    assert sent[0] == FEND
    assert sent[-1] == FEND
    assert sent[1] == 0x03  # port 3, command 0
    assert _kiss_unescape(sent[2:-1]) == payload


def test_kiss_client_send_frame_with_command() -> None:
    received_chunks: list[bytes] = []
    server_ready = threading.Event()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _run_server() -> None:
        server_ready.set()
        conn, _ = server.accept()
        try:
            data = conn.recv(1024)
            if data:
                received_chunks.append(data)
        finally:
            conn.close()
            server.close()

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    server_ready.wait(timeout=1)

    payload = b"cmd"
    client = KISSClient(KISSClientConfig(host="127.0.0.1", port=port, timeout=1.0))

    with client:
        client.send_frame(payload, port=1, command=KISSCommand.TX_DELAY)

    thread.join(timeout=1)
    assert received_chunks
    sent = received_chunks[0]
    assert sent[0] == FEND
    assert sent[-1] == FEND
    # command nibble 0x1 (TX_DELAY) combined with port 1 -> 0x11
    assert sent[1] == 0x11
    assert _kiss_unescape(sent[2:-1]) == payload


def test_kiss_client_connection_error() -> None:
    client = KISSClient(KISSClientConfig(host="127.0.0.1", port=65532, timeout=0.1))
    with pytest.raises(KISSClientError):
        client.connect()


@pytest.mark.parametrize("payload", [b"", b"abc", bytes([FEND, FESC, 0x10])])
def test_kiss_escape_roundtrip(payload: bytes) -> None:
    assert _kiss_unescape(_kiss_escape(payload)) == payload

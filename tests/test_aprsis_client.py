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

    thread.join(timeout=1)
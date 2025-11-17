from __future__ import annotations

import logging
import select
import termios
import threading
import tty
from datetime import datetime, timezone
from queue import Queue
from typing import Any, cast

from neo_rx.aprs.kiss_client import KISSClient, KISSClientError
from neo_rx.commands import listen


def test_apply_software_tocall_rewrites_destination() -> None:
    original = "CALL>DEST,PATH:payload"
    updated = listen._apply_software_tocall(original, "NEO123")
    assert updated.startswith("CALL>NEO123,PATH")
    assert updated.endswith(":payload")


def test_apply_software_tocall_ignores_malformed() -> None:
    assert listen._apply_software_tocall("invalid", "NEO123") == "invalid"
    assert listen._apply_software_tocall("SRC>DEST", "") == "SRC>DEST"


def test_extract_station_from_message() -> None:
    message = "[000001] port=0 CALL1>APRS something"
    assert listen._extract_station_from_message(message) == "CALL1"
    assert listen._extract_station_from_message("no station info") is None


def test_handle_keyboard_commands_prints_summary(tmp_path, capsys) -> None:
    log_path = tmp_path / "neo-rx.log"
    now = datetime.now(timezone.utc)
    log_path.write_text(
        f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} [000001] port=0 CALL>APRS:PAYLOAD\n",
        encoding="utf-8",
    )

    queue: "Queue[str]" = Queue()
    queue.put("s")
    listen._handle_keyboard_commands(queue, log_path)

    captured = capsys.readouterr()
    assert "Station activity summary" in captured.out
    assert "CALL" in captured.out


def test_handle_keyboard_commands_ignores_other_keys(tmp_path, capsys) -> None:
    log_path = tmp_path / "neo-rx.log"
    log_path.write_text("dummy", encoding="utf-8")

    queue: "Queue[str]" = Queue()
    queue.put("x")
    listen._handle_keyboard_commands(queue, log_path)

    captured = capsys.readouterr()
    assert captured.out == ""


def test_report_audio_error_logs(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="neo_rx.commands.listen")
    queue: "Queue[Exception]" = Queue()
    queue.put(RuntimeError("boom"))

    listen._report_audio_error(queue)

    assert "Audio pipeline error" in caplog.text


def test_wait_for_kiss_retries(monkeypatch) -> None:
    calls: list[int] = []

    class FlakyClient:
        def __init__(self) -> None:
            self.invocation = 0

        def connect(self) -> None:
            self.invocation += 1
            calls.append(self.invocation)
            if self.invocation < 3:
                raise KISSClientError("boom")

    monkeypatch.setattr(listen.time, "sleep", lambda *_: None)

    client = cast(KISSClient, FlakyClient())
    assert listen._wait_for_kiss(client, attempts=5, delay=0.01) is True
    assert calls == [1, 2, 3]


def test_wait_for_kiss_exhausts_attempts(monkeypatch) -> None:
    class AlwaysFail:
        def connect(self) -> None:
            raise KISSClientError("nope")

    monkeypatch.setattr(listen.time, "sleep", lambda *_: None)

    client = cast(KISSClient, AlwaysFail())
    result = listen._wait_for_kiss(client, attempts=2, delay=0.01)
    assert result is False


def test_apply_software_tocall_handles_missing_header() -> None:
    tnc2_line = "SRC:PAYLOAD>INFO"
    assert listen._apply_software_tocall(tnc2_line, "NEO123") == tnc2_line


def test_start_keyboard_listener_reads_keys(monkeypatch) -> None:
    stop_event = threading.Event()
    command_queue: "Queue[str]" = Queue()

    class FakeStdin:
        def __init__(self) -> None:
            self.calls = 0

        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 0

        def read(self, _size: int) -> str:
            self.calls += 1
            return "s" if self.calls == 1 else ""

    fake_stdin = FakeStdin()
    monkeypatch.setattr(listen.sys, "stdin", fake_stdin)

    select_calls = {"count": 0}

    def fake_select(_inputs, *_args):  # type: ignore[no-untyped-def]
        select_calls["count"] += 1
        if select_calls["count"] == 1:
            return ([fake_stdin], [], [])
        stop_event.set()
        raise ValueError("done")

    monkeypatch.setattr(select, "select", fake_select)
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: ["orig"])
    monkeypatch.setattr(termios, "tcsetattr", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tty, "setcbreak", lambda _fd: None)

    thread = listen._start_keyboard_listener(stop_event, command_queue)
    assert thread is not None
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert command_queue.get_nowait() == "s"

"""Tests for WSPR uploader queue and HTTP drain logic."""

import http.server
import json
import socketserver
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse


from neo_rx.wspr.uploader import (
    DAEMON_BACKOFF_BASE_S,
    WsprUploader,
)


class DummyResponse:
    def __init__(self, status_code=200, text="OK") -> None:
        self.status_code = status_code
        self.text = text


class DummySession:
    def __init__(self, response: DummyResponse) -> None:
        self._response = response
        self.calls: list[dict] = []
        self.headers: dict[str, str] = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self._response


def sample_spot(**overrides):
    spot = {
        "reporter_callsign": "N0CALL-10",
        "reporter_grid": "EM12ab",
        "reporter_power_dbm": 33,
        "dial_freq_hz": 14_080_000,
        "slot_start_utc": "2025-11-08T12:34:00Z",
        "freq_hz": 14_080_060,
        "call": "K1ABC",
        "grid": "FN42",
        "snr_db": -12.3,
        "dt": 0.5,
        "drift": -1,
    }
    spot.update(overrides)
    return spot


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.current = start

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


def test_enqueue_spot_creates_queue_file(tmp_path: Path):
    """Enqueue should create and append to queue file."""
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl")
    spot = {"call": "K1ABC", "freq_hz": 14080000, "snr_db": -12}
    uploader.enqueue_spot(spot)

    queue_file = tmp_path / "queue.jsonl"
    assert queue_file.exists()
    lines = queue_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["call"] == "K1ABC"


def test_read_queue_empty(tmp_path: Path):
    """Read from empty/missing queue should return empty list."""
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl")
    items = uploader._read_queue()
    assert items == []


def test_read_queue_multiple_items(tmp_path: Path):
    """Read should parse all JSON-lines in the queue."""
    queue_file = tmp_path / "queue.jsonl"
    spots = [
        {"call": "K1ABC", "freq_hz": 14080000},
        {"call": "K2DEF", "freq_hz": 14080100},
    ]
    with queue_file.open("w", encoding="utf-8") as fh:
        for spot in spots:
            fh.write(json.dumps(spot) + "\n")

    uploader = WsprUploader(queue_path=queue_file)
    items = uploader._read_queue()
    assert len(items) == 2
    assert items[0]["call"] == "K1ABC"
    assert items[1]["call"] == "K2DEF"


def test_rewrite_queue_replaces_atomically(tmp_path: Path):
    """Rewrite should replace queue with only remaining items."""
    queue_file = tmp_path / "queue.jsonl"
    initial = [
        {"call": "K1ABC", "freq_hz": 14080000},
        {"call": "K2DEF", "freq_hz": 14080100},
    ]
    with queue_file.open("w", encoding="utf-8") as fh:
        for item in initial:
            fh.write(json.dumps(item) + "\n")

    uploader = WsprUploader(queue_path=queue_file)
    # Keep only the second item
    remaining = [initial[1]]
    uploader._rewrite_queue(remaining)

    lines = queue_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["call"] == "K2DEF"


def test_drain_empty_queue():
    """Drain on empty queue should return zero counts."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        uploader = WsprUploader(queue_path=Path(tmp_dir) / "queue.jsonl")
        result = uploader.drain()
        assert result == {"attempted": 0, "succeeded": 0, "failed": 0}


def test_drain_all_succeed(tmp_path: Path, monkeypatch):
    """Drain should move all items to succeeded when upload_spot succeeds."""
    queue_file = tmp_path / "queue.jsonl"
    spots = [
        {"call": "K1ABC", "freq_hz": 14080000},
        {"call": "K2DEF", "freq_hz": 14080100},
    ]
    with queue_file.open("w", encoding="utf-8") as fh:
        for spot in spots:
            fh.write(json.dumps(spot) + "\n")

    uploader = WsprUploader(queue_path=queue_file)
    # Mock upload_spot to always succeed
    monkeypatch.setattr(uploader, "upload_spot", lambda spot: True)

    result = uploader.drain()
    assert result["attempted"] == 2
    assert result["succeeded"] == 2
    assert result["failed"] == 0

    # Queue should be empty after successful drain
    assert queue_file.read_text(encoding="utf-8").strip() == ""


def test_drain_partial_failure(tmp_path: Path, monkeypatch):
    """Drain should keep failed items in queue and count them."""
    queue_file = tmp_path / "queue.jsonl"
    spots = [
        {"call": "K1ABC", "freq_hz": 14080000},
        {"call": "K2DEF", "freq_hz": 14080100},
        {"call": "K3GHI", "freq_hz": 14080200},
    ]
    with queue_file.open("w", encoding="utf-8") as fh:
        for spot in spots:
            fh.write(json.dumps(spot) + "\n")

    uploader = WsprUploader(queue_path=queue_file)

    # Mock to fail on second item
    call_count = [0]

    def mock_upload(spot):
        call_count[0] += 1
        return call_count[0] != 2  # fail on 2nd call

    monkeypatch.setattr(uploader, "upload_spot", mock_upload)

    result = uploader.drain()
    assert result["attempted"] == 3
    assert result["succeeded"] == 2
    assert result["failed"] == 1

    # Queue should contain only the failed spot
    lines = queue_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["call"] == "K2DEF"


def test_drain_max_items_limit(tmp_path: Path, monkeypatch):
    """Drain with max_items should limit attempts and keep remainder in queue."""
    queue_file = tmp_path / "queue.jsonl"
    spots = [
        {"call": "K1ABC", "freq_hz": 14080000},
        {"call": "K2DEF", "freq_hz": 14080100},
        {"call": "K3GHI", "freq_hz": 14080200},
    ]
    with queue_file.open("w", encoding="utf-8") as fh:
        for spot in spots:
            fh.write(json.dumps(spot) + "\n")

    uploader = WsprUploader(queue_path=queue_file)
    monkeypatch.setattr(uploader, "upload_spot", lambda spot: True)

    result = uploader.drain(max_items=2)
    assert result["attempted"] == 2
    assert result["succeeded"] == 2
    # "failed" includes unattempted items that remain in queue (K3GHI)
    assert result["failed"] == 1

    # Queue should contain the third item (not attempted)
    lines = queue_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["call"] == "K3GHI"


def test_drain_exception_handling(tmp_path: Path, monkeypatch):
    """Drain should keep items in queue if upload_spot throws."""
    queue_file = tmp_path / "queue.jsonl"
    spots = [
        {"call": "K1ABC", "freq_hz": 14080000},
        {"call": "K2DEF", "freq_hz": 14080100},
    ]
    with queue_file.open("w", encoding="utf-8") as fh:
        for spot in spots:
            fh.write(json.dumps(spot) + "\n")

    uploader = WsprUploader(queue_path=queue_file)

    # Mock to raise on first item
    call_count = [0]

    def mock_upload(spot):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Network error")
        return True

    monkeypatch.setattr(uploader, "upload_spot", mock_upload)

    result = uploader.drain()
    assert result["attempted"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1

    # Queue should contain only the item that threw
    lines = queue_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["call"] == "K1ABC"


def test_upload_spot_success_builds_params(tmp_path: Path):
    session = DummySession(DummyResponse(200, "OK"))
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl", session=session)

    ok = uploader.upload_spot(sample_spot())

    assert ok is True
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == uploader.base_url
    assert call["timeout"] == (5, 10)
    params = call["params"]
    assert params["function"] == "wspr"
    assert params["rcall"] == "N0CALL-10"
    assert params["rqrg"] == "14.080000"
    assert params["tqrg"] == "14.080060"
    assert params["sig"] == "-12"
    assert params["dt"] == "0.5"
    assert params["date"] == "251108"
    assert params["time"] == "1234"


def test_upload_spot_missing_metadata_skips_request(tmp_path: Path):
    session = DummySession(DummyResponse(200, "OK"))
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl", session=session)

    spot = sample_spot(reporter_grid=None)
    ok = uploader.upload_spot(spot)

    assert ok is False
    assert session.calls == []


def test_upload_spot_http_error(tmp_path: Path):
    session = DummySession(DummyResponse(500, "ERR"))
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl", session=session)

    ok = uploader.upload_spot(sample_spot())

    assert ok is False
    assert len(session.calls) == 1


def test_upload_spot_empty_body(tmp_path: Path):
    session = DummySession(DummyResponse(200, ""))
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl", session=session)

    ok = uploader.upload_spot(sample_spot())

    assert ok is False
    assert len(session.calls) == 1


def test_drain_records_first_failure_message(tmp_path: Path, monkeypatch):
    queue_file = tmp_path / "queue.jsonl"
    uploader = WsprUploader(queue_path=queue_file)
    uploader.enqueue_spot({"call": "K1ABC"})
    uploader.enqueue_spot({"call": "K2DEF"})

    def mock_upload(spot):
        uploader._last_upload_error = f"boom {spot['call']}"  # noqa: SLF001 - intentional for test
        return False

    monkeypatch.setattr(uploader, "upload_spot", mock_upload)

    result = uploader.drain()

    assert result["failed"] == 2
    assert result.get("last_error") == "boom K1ABC"


def test_drain_daemon_backoff_skips_until_ready(tmp_path: Path, monkeypatch):
    queue_file = tmp_path / "queue.jsonl"
    clock = FakeClock()
    uploader = WsprUploader(queue_path=queue_file, clock=clock)
    uploader.enqueue_spot({"call": "K1ABC"})

    call_count = {"count": 0}

    def mock_upload(spot):
        call_count["count"] += 1
        uploader._last_upload_error = "boom"  # noqa: SLF001 - intentional for test
        return False

    monkeypatch.setattr(uploader, "upload_spot", mock_upload)

    first = uploader.drain(daemon=True)
    assert first["attempted"] == 1
    assert first["failed"] == 1
    assert first.get("backoff_seconds") == DAEMON_BACKOFF_BASE_S
    assert first.get("last_error") == "boom"

    skipped = uploader.drain(daemon=True)
    assert skipped["attempted"] == 0
    assert skipped["failed"] == 1
    assert skipped.get("skipped_due_to_backoff") is True
    assert skipped.get("next_attempt_in", 0) > 0
    assert call_count["count"] == 1

    clock.advance(DAEMON_BACKOFF_BASE_S)
    again = uploader.drain(daemon=True)
    assert again["attempted"] == 1
    assert call_count["count"] == 2


def test_drain_daemon_backoff_resets_after_success(tmp_path: Path, monkeypatch):
    queue_file = tmp_path / "queue.jsonl"
    clock = FakeClock()
    uploader = WsprUploader(queue_path=queue_file, clock=clock)
    uploader.enqueue_spot({"call": "K1ABC"})

    outcomes = iter([False, True, True])

    def mock_upload(_spot):
        result = next(outcomes)
        uploader._last_upload_error = None
        if not result:
            uploader._last_upload_error = "boom"  # noqa: SLF001 - intentional for test
        return result

    monkeypatch.setattr(uploader, "upload_spot", mock_upload)

    first = uploader.drain(daemon=True)
    assert first.get("backoff_seconds") == DAEMON_BACKOFF_BASE_S

    # Still within backoff window -> skip
    skipped = uploader.drain(daemon=True)
    assert skipped.get("skipped_due_to_backoff") is True

    clock.advance(DAEMON_BACKOFF_BASE_S)
    second = uploader.drain(daemon=True)
    assert "backoff_seconds" not in second
    assert second["failed"] == 0

    uploader.enqueue_spot({"call": "K9ZZZ"})
    immediate = uploader.drain(daemon=True)
    assert immediate["attempted"] == 1
    assert immediate.get("skipped_due_to_backoff") is None


def test_send_heartbeat_success(tmp_path: Path):
    session = DummySession(DummyResponse(200, "OK"))
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl", session=session)

    ok = uploader.send_heartbeat(
        reporter_call="N0CALL-10",
        reporter_grid="EM12ab",
        dial_freq_hz=14_095_600,
        reporter_power_dbm=37,
        percent_time=92.0,
    )

    assert ok is True
    assert len(session.calls) == 1
    params = session.calls[0]["params"]
    assert params["function"] == "wsprstat"
    assert params["tpct"] == "92"
    assert params["rqrg"].startswith("14.095")


def test_send_heartbeat_missing_metadata(tmp_path: Path):
    session = DummySession(DummyResponse(200, "OK"))
    uploader = WsprUploader(queue_path=tmp_path / "queue.jsonl", session=session)

    ok = uploader.send_heartbeat(
        reporter_call="",
        reporter_grid="",
        dial_freq_hz=14_095_600,
        reporter_power_dbm=37,
        percent_time=100.0,
    )

    assert ok is False
    assert session.calls == []
    assert uploader.last_error is not None


def test_upload_spot_against_live_http_server(tmp_path: Path):
    class Handler(http.server.BaseHTTPRequestHandler):
        requests: list[str] = []

        def do_GET(self):  # type: ignore[override]
            Handler.requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format: str, *args):  # noqa: A003 - silence server logs
            return

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        uploader = WsprUploader(
            queue_path=tmp_path / "queue.jsonl",
            base_url=f"http://127.0.0.1:{port}/upload",
        )

        ok = uploader.upload_spot(sample_spot())

        server.shutdown()
        thread.join(timeout=2)

    assert ok is True
    assert Handler.requests, "HTTP server did not receive any requests"
    parsed = urlparse(Handler.requests[0])
    params = parse_qs(parsed.query)
    assert params["function"] == ["wspr"]
    assert params["tcall"] == ["K1ABC"]

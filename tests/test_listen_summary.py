from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from neo_aprs.commands.listen import _summarize_recent_activity


def test_summarize_recent_activity_filters_recent(tmp_path) -> None:
    log_path = tmp_path / "neo-rx.log"
    now = datetime(2025, 10, 30, 12, 0, tzinfo=timezone.utc)

    lines = [
        f"{(now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')} [000001] port=0 CALL1>APRS:PAYLOAD",  # recent
        f"{(now - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')} [000002] port=0 CALL2>APRS:PAYLOAD",  # recent
        f"{(now - timedelta(hours=25)).strftime('%Y-%m-%dT%H:%M:%SZ')} [000003] port=0 OLD>APRS:PAYLOAD",  # stale
        f"{(now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')} [stats 2025-10-30T11:00:00Z] frames=3 aprs_ok=2 aprs_fail=1",
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = _summarize_recent_activity(log_path, window=timedelta(hours=24), now=now)

    assert "Unique stations: 2" in summary
    assert "CALL1" in summary
    assert "CALL2" in summary
    assert "OLD" not in summary


def test_summarize_recent_activity_missing_log(tmp_path) -> None:
    log_path = tmp_path / "neo-rx.log"
    summary = _summarize_recent_activity(log_path, window=timedelta(hours=24))
    assert "No listener log file" in summary


def test_summarize_recent_activity_handles_invalid_lines(tmp_path) -> None:
    log_path = tmp_path / "neo-rx.log"
    now = datetime(2025, 10, 30, 12, 0, tzinfo=timezone.utc)
    contents = [
        "garbled",  # split failure
        f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} not_a_frame",  # missing [
        "not-a-time [000001] port=0 CALL>APRS:PAYLOAD",  # timestamp parse error
        f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} [000002] other CALL>APRS:PAYLOAD",  # missing port marker
    ]
    log_path.write_text("\n".join(contents), encoding="utf-8")

    summary = _summarize_recent_activity(log_path, window=timedelta(hours=24), now=now)

    assert summary.startswith("No stations heard")


def test_summarize_recent_activity_updates_existing_station(tmp_path) -> None:
    log_path = tmp_path / "neo-rx.log"
    now = datetime(2025, 10, 30, 12, 0, tzinfo=timezone.utc)

    entries = [
        f"{(now - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')} [000001] port=0 CALL>APRS:PAYLOAD",
        f"{(now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')} [000002] port=0 CALL>APRS:PAYLOAD",
    ]
    log_path.write_text("\n".join(entries), encoding="utf-8")

    summary = _summarize_recent_activity(log_path, window=timedelta(hours=24), now=now)

    assert "Unique stations: 1" in summary
    assert "CALL" in summary
    assert "frames" in summary


def test_summarize_recent_activity_handles_oserror(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "neo-rx.log"
    log_path.write_text("", encoding="utf-8")

    original_open = Path.open

    def fake_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == log_path:
            raise OSError("denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    summary = _summarize_recent_activity(log_path, window=timedelta(hours=24))

    assert "Unable to read listener log" in summary


def test_summarize_recent_activity_truncates_rows(tmp_path) -> None:
    log_path = tmp_path / "neo-rx.log"
    now = datetime(2025, 10, 30, 12, 0, tzinfo=timezone.utc)

    lines = [
        f"{(now - timedelta(minutes=i)).strftime('%Y-%m-%dT%H:%M:%SZ')} [000{i:03d}] port=0 CALL{i}>APRS:PAYLOAD"
        for i in range(20)
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")

    summary = _summarize_recent_activity(log_path, window=timedelta(hours=24), now=now)

    assert "plus 5 more" in summary

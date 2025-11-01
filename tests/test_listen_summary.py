from __future__ import annotations

from datetime import datetime, timedelta, timezone

from neo_igate.commands.listen import _summarize_recent_activity


def test_summarize_recent_activity_filters_recent(tmp_path) -> None:
    log_path = tmp_path / "neo-igate.log"
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
    log_path = tmp_path / "neo-igate.log"
    summary = _summarize_recent_activity(log_path, window=timedelta(hours=24))
    assert "No listener log file" in summary

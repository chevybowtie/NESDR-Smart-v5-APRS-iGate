"""Tests for WSPR uploader queue and drain logic."""

import json
from pathlib import Path

import pytest

from neo_igate.wspr.uploader import WsprUploader


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

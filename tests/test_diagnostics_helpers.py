"""Tests for diagnostics helper utilities."""

from __future__ import annotations

from nesdr_igate import diagnostics_helpers as helpers


def test_probe_tcp_endpoint_success(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class DummyConnection:
        def __enter__(self) -> "DummyConnection":
            calls["entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
            calls["exited"] = True
            return None

    times = iter([100.0, 100.123])

    def fake_perf_counter() -> float:
        return next(times)

    def fake_create_connection(address, timeout=None):  # type: ignore[no-untyped-def]
        calls["address"] = address
        calls["timeout"] = timeout
        return DummyConnection()

    monkeypatch.setattr(helpers.time, "perf_counter", fake_perf_counter)
    monkeypatch.setattr(helpers.socket, "create_connection", fake_create_connection)

    result = helpers.probe_tcp_endpoint("example.com", 14580, timeout=2.5)

    assert result.success is True
    assert result.error is None
    assert result.latency_ms == 123.0
    assert calls["address"] == ("example.com", 14580)
    assert calls["timeout"] == 2.5
    assert calls["entered"] and calls["exited"]


def test_probe_tcp_endpoint_failure(monkeypatch) -> None:
    def fake_create_connection(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("connection refused")

    monkeypatch.setattr(helpers.socket, "create_connection", fake_create_connection)

    result = helpers.probe_tcp_endpoint("bad.example", 9999, timeout=0.1)

    assert result.success is False
    assert result.latency_ms is None
    assert "connection refused" in (result.error or "")

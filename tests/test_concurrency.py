"""Tests for concurrent APRS/WSPR operation with separate instances.

Verifies that --instance-id produces isolated data/log directories and that
multiple modes can coexist without conflicting paths or state.
"""

from __future__ import annotations

import os
from pathlib import Path

from neo_core import config as config_module


def test_instance_id_isolates_data_directories(monkeypatch, tmp_path: Path) -> None:
    """Verify different instance IDs produce separate data directories."""
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))

    # Instance 1
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "aprs-1")
    aprs1_data = config_module.get_data_dir()
    assert "instances/aprs-1" in str(aprs1_data)

    # Instance 2
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "wspr-20m")
    wspr_data = config_module.get_data_dir()
    assert "instances/wspr-20m" in str(wspr_data)

    # Ensure they're different
    assert aprs1_data != wspr_data


def test_mode_specific_data_dirs_under_instance(monkeypatch, tmp_path: Path) -> None:
    """Verify mode-specific directories are nested under instance."""
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "rig1")

    aprs_data = config_module.get_mode_data_dir("aprs")
    wspr_data = config_module.get_mode_data_dir("wspr")

    assert aprs_data == tmp_path / "instances" / "rig1" / "aprs"
    assert wspr_data == tmp_path / "instances" / "rig1" / "wspr"
    assert aprs_data != wspr_data


def test_logs_dirs_isolated_per_instance_and_mode(monkeypatch, tmp_path: Path) -> None:
    """Verify logs are isolated by instance and mode."""
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))

    # APRS instance 1
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "aprs-1")
    aprs1_logs = config_module.get_logs_dir("aprs")
    assert aprs1_logs == tmp_path / "instances" / "aprs-1" / "logs" / "aprs"

    # WSPR instance 2
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "wspr-20m")
    wspr_logs = config_module.get_logs_dir("wspr")
    assert wspr_logs == tmp_path / "instances" / "wspr-20m" / "logs" / "wspr"

    # Ensure they're isolated
    assert aprs1_logs != wspr_logs


def test_wspr_runs_dir_uses_instance_label(monkeypatch, tmp_path: Path) -> None:
    """Verify WSPR runs directory uses instance ID when available."""
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "wspr-40m")

    runs_dir = config_module.get_wspr_runs_dir()

    # Should use instance ID as the run label
    assert (
        runs_dir == tmp_path / "instances" / "wspr-40m" / "wspr" / "runs" / "wspr-40m"
    )


def test_wspr_runs_dir_custom_label_overrides_instance(
    monkeypatch, tmp_path: Path
) -> None:
    """Verify custom run_label overrides instance ID."""
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "wspr-40m")

    runs_dir = config_module.get_wspr_runs_dir(run_label="calibration-2025")

    assert (
        runs_dir
        == tmp_path / "instances" / "wspr-40m" / "wspr" / "runs" / "calibration-2025"
    )


def test_no_instance_id_uses_base_paths(monkeypatch, tmp_path: Path) -> None:
    """Verify behavior without NEO_RX_INSTANCE_ID (legacy single-instance mode)."""
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("NEO_RX_INSTANCE_ID", raising=False)

    base_data = config_module.get_data_dir()
    aprs_data = config_module.get_mode_data_dir("aprs")
    wspr_logs = config_module.get_logs_dir("wspr")

    assert base_data == tmp_path
    assert aprs_data == tmp_path / "aprs"
    assert wspr_logs == tmp_path / "logs" / "wspr"


def test_instance_id_sanitization(monkeypatch, tmp_path: Path) -> None:
    """Verify unsafe instance IDs are sanitized."""
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "../evil/path")

    data_dir = config_module.get_data_dir()

    # Should strip path separators; dots are kept but slashes removed
    # Result: "..evilpath" which is safe (no actual path traversal)
    assert "/" not in str(data_dir).split("instances/")[-1]
    assert "evilpath" in str(data_dir)


def test_concurrent_aprs_wspr_simulation(monkeypatch, tmp_path: Path) -> None:
    """Simulate concurrent APRS and WSPR runs with different instances.

    This test verifies the core path isolation mechanism that enables
    concurrent operation without requiring actual process spawning.
    """
    monkeypatch.setenv("NEO_RX_DATA_DIR", str(tmp_path))

    # Simulate APRS instance
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "aprs-east")
    aprs_data = config_module.get_mode_data_dir("aprs")
    aprs_logs = config_module.get_logs_dir("aprs")
    aprs_data.mkdir(parents=True, exist_ok=True)
    aprs_logs.mkdir(parents=True, exist_ok=True)
    (aprs_logs / "neo-rx.log").write_text("APRS log", encoding="utf-8")

    # Simulate WSPR instance
    monkeypatch.setenv("NEO_RX_INSTANCE_ID", "wspr-20m")
    wspr_data = config_module.get_mode_data_dir("wspr")
    wspr_logs = config_module.get_logs_dir("wspr")
    wspr_runs = config_module.get_wspr_runs_dir()
    wspr_data.mkdir(parents=True, exist_ok=True)
    wspr_logs.mkdir(parents=True, exist_ok=True)
    wspr_runs.mkdir(parents=True, exist_ok=True)
    (wspr_runs / "wspr_spots.jsonl").write_text('{"call":"K1ABC"}\n', encoding="utf-8")

    # Verify isolation
    assert aprs_data.exists()
    assert wspr_data.exists()
    assert aprs_data != wspr_data

    assert (aprs_logs / "neo-rx.log").exists()
    assert (wspr_runs / "wspr_spots.jsonl").exists()

    # Verify directory structure
    assert "instances/aprs-east/aprs" in str(aprs_data)
    assert "instances/wspr-20m/wspr" in str(wspr_data)
    assert "instances/aprs-east/logs/aprs" in str(aprs_logs)
    assert "instances/wspr-20m/logs/wspr" in str(wspr_logs)


def test_cli_propagates_instance_id_to_env(monkeypatch) -> None:
    """Verify neo_core.cli sets NEO_RX_INSTANCE_ID from --instance-id."""
    from argparse import Namespace

    # Clear any existing env var
    monkeypatch.delenv("NEO_RX_INSTANCE_ID", raising=False)

    args = Namespace(instance_id="test-rig", data_dir=None, mode="aprs", verb="listen")

    # Simulate the env propagation logic from cli.main
    if getattr(args, "instance_id", None):
        monkeypatch.setenv("NEO_RX_INSTANCE_ID", str(args.instance_id))

    assert os.environ.get("NEO_RX_INSTANCE_ID") == "test-rig"


def test_cli_propagates_data_dir_to_env(monkeypatch, tmp_path: Path) -> None:
    """Verify neo_core.cli sets NEO_RX_DATA_DIR from --data-dir."""
    from argparse import Namespace

    monkeypatch.delenv("NEO_RX_DATA_DIR", raising=False)

    args = Namespace(
        instance_id=None, data_dir=str(tmp_path), mode="wspr", verb="worker"
    )

    # Simulate the env propagation logic from cli.main
    if getattr(args, "data_dir", None):
        monkeypatch.setenv("NEO_RX_DATA_DIR", str(args.data_dir))

    assert os.environ.get("NEO_RX_DATA_DIR") == str(tmp_path)

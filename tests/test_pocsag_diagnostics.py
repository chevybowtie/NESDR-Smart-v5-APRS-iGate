"""Tests for POCSAG diagnostics."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
from argparse import Namespace

from neo_pocsag.pocsag.diagnostics import run_diagnostics
from neo_pocsag.commands.diagnostics import run_diagnostics_command


class TestPocsagDiagnostics:
    """Test POCSAG diagnostics functionality."""

    @patch("shutil.which")
    def test_check_multimon_ng_found(self, mock_which) -> None:
        """Test multimon-ng check when found."""
        mock_which.return_value = "/usr/bin/multimon-ng"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="POCSAG", stderr="")
            report = run_diagnostics()
            assert len(report.checks) == 2
            multimon_check = next(c for c in report.checks if c.name == "multimon_ng")
            assert multimon_check.status == "OK"

    @patch("shutil.which")
    def test_check_multimon_ng_not_found(self, mock_which) -> None:
        """Test multimon-ng check when not found."""
        mock_which.return_value = None

        report = run_diagnostics()
        multimon_check = next(c for c in report.checks if c.name == "multimon_ng")
        assert multimon_check.status == "ERROR"

    @patch("shutil.which")
    def test_check_rtl_sdr_found(self, mock_which) -> None:
        """Test RTL-SDR check when found."""
        mock_which.return_value = "/usr/bin/rtl_test"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            report = run_diagnostics()
            rtl_check = next(c for c in report.checks if c.name == "rtl_sdr")
            assert rtl_check.status == "OK"


class TestPocsagDiagnosticsCommand:
    """Test POCSAG diagnostics command."""

    @patch("neo_pocsag.commands.diagnostics.run_diagnostics")
    def test_run_diagnostics_command(self, mock_run_diagnostics) -> None:
        """Test diagnostics command execution."""
        # Mock the report
        mock_report = Mock()
        mock_report.ok = True
        mock_check = Mock()
        mock_check.name = "test_check"
        mock_check.status = "OK"
        mock_check.message = "Test passed"
        mock_check.details = {"version": "1.0"}
        mock_report.checks = [mock_check]
        mock_run_diagnostics.return_value = mock_report

        args = Namespace()

        with patch("builtins.print"):  # Suppress print output
            result = run_diagnostics_command(args)

        assert result == 0
        mock_run_diagnostics.assert_called_once()
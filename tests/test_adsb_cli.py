"""Tests for ADS-B CLI commands."""

import argparse
from unittest.mock import patch, MagicMock

import pytest

from neo_core.cli import build_parser


class TestAdsbCli:
    """Tests for ADS-B CLI commands."""

    def test_parser_has_adsb_mode(self):
        """Test that parser includes adsb mode."""
        parser = build_parser()
        # Parse adsb help
        with pytest.raises(SystemExit):
            parser.parse_args(["adsb", "--help"])

    def test_adsb_listen_command(self):
        """Test adsb listen command parsing."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "listen"])
        assert args.mode == "adsb"
        assert args.verb == "listen"
        assert args.json_path == "/run/dump1090-fa/aircraft.json"
        assert args.poll_interval == 1.0

    def test_adsb_listen_custom_json_path(self):
        """Test adsb listen with custom JSON path."""
        parser = build_parser()
        args = parser.parse_args([
            "adsb", "listen",
            "--json-path", "/custom/aircraft.json"
        ])
        assert args.json_path == "/custom/aircraft.json"

    def test_adsb_listen_custom_poll_interval(self):
        """Test adsb listen with custom poll interval."""
        parser = build_parser()
        args = parser.parse_args([
            "adsb", "listen",
            "--poll-interval", "2.5"
        ])
        assert args.poll_interval == 2.5

    def test_adsb_listen_quiet_mode(self):
        """Test adsb listen with quiet mode."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "listen", "--quiet"])
        assert args.quiet

    def test_adsb_diagnostics_command(self):
        """Test adsb diagnostics command parsing."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "diagnostics"])
        assert args.mode == "adsb"
        assert args.verb == "diagnostics"

    def test_adsb_diagnostics_json_output(self):
        """Test adsb diagnostics with JSON output."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "diagnostics", "--json"])
        assert args.json

    def test_adsb_diagnostics_verbose(self):
        """Test adsb diagnostics with verbose mode."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "diagnostics", "--verbose"])
        assert args.verbose

    def test_adsb_diagnostics_no_adsbexchange(self):
        """Test adsb diagnostics skipping ADS-B Exchange."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "diagnostics", "--no-adsbexchange"])
        assert args.no_adsbexchange

    def test_adsb_setup_command(self):
        """Test adsb setup command parsing."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "setup"])
        assert args.mode == "adsb"
        assert args.verb == "setup"

    def test_adsb_setup_reset(self):
        """Test adsb setup with reset flag."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "setup", "--reset"])
        assert args.reset

    def test_adsb_setup_non_interactive(self):
        """Test adsb setup with non-interactive flag."""
        parser = build_parser()
        args = parser.parse_args(["adsb", "setup", "--non-interactive"])
        assert args.non_interactive

    def test_adsb_common_flags(self):
        """Test common flags are available for adsb commands."""
        parser = build_parser()
        args = parser.parse_args([
            "adsb", "listen",
            "--device-id", "12345",
            "--instance-id", "adsb-1",
            "--config", "/custom/config.toml",
            "--data-dir", "/custom/data",
            "--log-level", "debug",
        ])
        assert args.device_id == "12345"
        assert args.instance_id == "adsb-1"
        assert args.config == "/custom/config.toml"
        assert args.data_dir == "/custom/data"
        assert args.log_level == "debug"


class TestAdsbDiagnosticsCommand:
    """Tests for ADS-B diagnostics command execution."""

    @patch("neo_adsb.commands.diagnostics.run_diagnostics")
    def test_diagnostics_command_runs(self, mock_run_diagnostics):
        """Test that diagnostics command calls run_diagnostics."""
        from neo_adsb.adsb.diagnostics import DiagnosticsReport, DiagnosticResult

        mock_report = DiagnosticsReport()
        mock_report.checks.append(DiagnosticResult("test", "OK", "Test passed"))
        mock_run_diagnostics.return_value = mock_report

        from neo_adsb.commands.diagnostics import run_diagnostics_cmd

        args = argparse.Namespace(
            json_path=None,
            no_adsbexchange=False,
            json=True,
            verbose=False,
        )

        result = run_diagnostics_cmd(args)
        assert result == 0
        mock_run_diagnostics.assert_called_once()

    @patch("neo_adsb.commands.diagnostics.run_diagnostics")
    def test_diagnostics_command_returns_error_on_failure(self, mock_run_diagnostics):
        """Test that diagnostics command returns 1 on failure."""
        from neo_adsb.adsb.diagnostics import DiagnosticsReport, DiagnosticResult

        mock_report = DiagnosticsReport()
        mock_report.checks.append(DiagnosticResult("test", "ERROR", "Test failed"))
        mock_run_diagnostics.return_value = mock_report

        from neo_adsb.commands.diagnostics import run_diagnostics_cmd

        args = argparse.Namespace(
            json_path=None,
            no_adsbexchange=False,
            json=True,
            verbose=False,
        )

        result = run_diagnostics_cmd(args)
        assert result == 1

"""Tests for POCSAG scan command."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
from argparse import Namespace

from neo_pocsag.commands.scan import run_scan


class TestPocsagScan:
    """Test POCSAG scan command."""

    @patch("neo_pocsag.pocsag.scan.scan_frequencies")
    @patch("neo_pocsag.commands.scan.LOG")
    def test_run_scan_no_activity(self, mock_log, mock_scan_frequencies) -> None:
        """Test scan command with no activity found."""
        # Mock scan results - no messages
        mock_scan_frequencies.return_value = [
            {"frequency_hz": 152840000, "message_count": 0, "messages_per_min": 0.0, "unique_addresses": 0},
            {"frequency_hz": 152850000, "message_count": 0, "messages_per_min": 0.0, "unique_addresses": 0},
        ]

        args = Namespace(
            start_frequency=152840000,
            end_frequency=152850000,
            step_hz=10000,
            dwell_seconds=120,
            gain=None,
            ppm=0,
            device_index=0,
            json=False,
        )

        result = run_scan(args)

        assert result == 0
        mock_scan_frequencies.assert_called_once()
        mock_log.info.assert_any_call("No POCSAG activity detected in scanned range")

    @patch("neo_pocsag.pocsag.scan.scan_frequencies")
    @patch("neo_pocsag.commands.scan.LOG")
    def test_run_scan_with_activity(self, mock_log, mock_scan_frequencies) -> None:
        """Test scan command with activity found."""
        # Mock scan results - some messages
        mock_scan_frequencies.return_value = [
            {"frequency_hz": 152840000, "message_count": 5, "messages_per_min": 2.5, "unique_addresses": 3},
            {"frequency_hz": 152850000, "message_count": 0, "messages_per_min": 0.0, "unique_addresses": 0},
        ]

        args = Namespace(
            start_frequency=152840000,
            end_frequency=152850000,
            step_hz=10000,
            dwell_seconds=120,
            gain=None,
            ppm=0,
            device_index=0,
            json=False,
        )

        result = run_scan(args)

        assert result == 0
        mock_log.info.assert_any_call("Found POCSAG activity on %d frequencies:", 1)
        mock_log.info.assert_any_call("%.3f MHz: %d messages, %d unique addresses", 152.84, 5, 3)

    @patch("neo_pocsag.pocsag.scan.scan_frequencies")
    def test_run_scan_json_output(self, mock_scan_frequencies) -> None:
        """Test scan command with JSON output."""
        mock_scan_frequencies.return_value = [
            {"frequency_hz": 152840000, "message_count": 1, "messages_per_min": 0.5, "unique_addresses": 1},
        ]

        args = Namespace(
            start_frequency=152840000,
            end_frequency=152850000,
            step_hz=10000,
            dwell_seconds=120,
            gain=None,
            ppm=0,
            device_index=0,
            json=True,
        )

        with patch("builtins.print") as mock_print:
            result = run_scan(args)

        assert result == 0
        mock_print.assert_called_once()
        # Check that print was called with JSON data
        printed_data = mock_print.call_args[0][0]
        assert '"frequency_hz": 152840000' in printed_data
        assert '"message_count": 1' in printed_data
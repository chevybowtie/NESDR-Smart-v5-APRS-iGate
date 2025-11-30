"""Tests for ADS-B diagnostics functionality."""

import json
from pathlib import Path
import tempfile

import pytest

from neo_adsb.adsb.diagnostics import (
    DiagnosticResult,
    DiagnosticsReport,
    check_dump1090_json,
    run_diagnostics,
)


class TestDiagnosticResult:
    """Tests for DiagnosticResult dataclass."""

    def test_result_creation(self):
        """Test creating a diagnostic result."""
        result = DiagnosticResult(
            name="test_check",
            status="OK",
            message="Test passed",
        )
        assert result.name == "test_check"
        assert result.status == "OK"
        assert result.message == "Test passed"
        assert result.details == {}

    def test_result_with_details(self):
        """Test creating a diagnostic result with details."""
        result = DiagnosticResult(
            name="test_check",
            status="WARNING",
            message="Test warning",
            details={"key": "value"},
        )
        assert result.details == {"key": "value"}


class TestDiagnosticsReport:
    """Tests for DiagnosticsReport dataclass."""

    def test_empty_report_is_ok(self):
        """Test that empty report is considered OK."""
        report = DiagnosticsReport()
        assert report.ok
        assert not report.has_errors

    def test_report_with_ok_checks(self):
        """Test report with all OK checks."""
        report = DiagnosticsReport()
        report.checks.append(DiagnosticResult("check1", "OK", "Good"))
        report.checks.append(DiagnosticResult("check2", "OK", "Good"))
        assert report.ok
        assert not report.has_errors

    def test_report_with_warning(self):
        """Test report with warning."""
        report = DiagnosticsReport()
        report.checks.append(DiagnosticResult("check1", "OK", "Good"))
        report.checks.append(DiagnosticResult("check2", "WARNING", "Warning"))
        assert not report.ok
        assert not report.has_errors

    def test_report_with_error(self):
        """Test report with error."""
        report = DiagnosticsReport()
        report.checks.append(DiagnosticResult("check1", "OK", "Good"))
        report.checks.append(DiagnosticResult("check2", "ERROR", "Error"))
        assert not report.ok
        assert report.has_errors

    def test_report_to_dict(self):
        """Test report serialization to dict."""
        report = DiagnosticsReport()
        report.checks.append(DiagnosticResult("check1", "OK", "Good"))

        result = report.to_dict()
        assert "timestamp" in result
        assert result["status"] == "OK"
        assert len(result["checks"]) == 1
        assert result["checks"][0]["name"] == "check1"


class TestDump1090JsonCheck:
    """Tests for dump1090 JSON check."""

    def test_check_missing_file(self):
        """Test check when JSON file is missing."""
        result = check_dump1090_json("/nonexistent/aircraft.json")
        assert result.status == "ERROR"
        assert "not found" in result.message.lower()

    def test_check_valid_json(self):
        """Test check with valid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "now": 1700000000.0,
                "aircraft": [
                    {"hex": "abc123"},
                    {"hex": "def456"},
                ]
            }, f)
            temp_path = f.name

        try:
            result = check_dump1090_json(temp_path)
            assert result.status == "OK"
            assert "2 aircraft" in result.message
            assert result.details["aircraft_count"] == 2
        finally:
            Path(temp_path).unlink()

    def test_check_invalid_json(self):
        """Test check with invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            temp_path = f.name

        try:
            result = check_dump1090_json(temp_path)
            assert result.status == "ERROR"
            assert "Invalid JSON" in result.message
        finally:
            Path(temp_path).unlink()


class TestRunDiagnostics:
    """Tests for the full diagnostics run."""

    def test_run_diagnostics_defaults(self):
        """Test running diagnostics with defaults."""
        report = run_diagnostics(check_adsbexchange=False)
        assert isinstance(report, DiagnosticsReport)
        assert len(report.checks) >= 3  # dump1090 installed, running, json

    def test_run_diagnostics_with_custom_json_path(self):
        """Test running diagnostics with custom JSON path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"now": 1700000000.0, "aircraft": []}, f)
            temp_path = f.name

        try:
            report = run_diagnostics(
                check_adsbexchange=False,
                json_path=temp_path,
            )
            # Find the json check
            json_check = next(c for c in report.checks if c.name == "dump1090_json")
            assert json_check.status == "OK"
        finally:
            Path(temp_path).unlink()

    def test_run_diagnostics_with_adsbexchange(self):
        """Test running diagnostics with ADS-B Exchange checks."""
        report = run_diagnostics(check_adsbexchange=True)
        assert isinstance(report, DiagnosticsReport)
        # Should include adsbexchange checks
        check_names = [c.name for c in report.checks]
        assert "adsbexchange" in check_names
        assert "adsbexchange_services" in check_names

"""Tests for POCSAG capture functionality."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from neo_pocsag.pocsag.capture import PocsagCapture, PocsagMessage


class TestPocsagMessage:
    """Test PocsagMessage dataclass."""

    def test_message_creation(self) -> None:
        """Test creating a POCSAG message."""
        msg = PocsagMessage(
            address=1234567,
            function=0,
            message_type="alpha",
            message="Hello World",
        )
        assert msg.address == 1234567
        assert msg.function == 0
        assert msg.message_type == "alpha"
        assert msg.message == "Hello World"


class TestPocsagCapture:
    """Test PocsagCapture class."""

    def test_init(self) -> None:
        """Test capture initialization."""
        capture = PocsagCapture(frequency_hz=152840000)
        assert capture._frequency_hz == 152840000
        assert not capture.is_running()

    def test_parse_multimon_line_alpha(self) -> None:
        """Test parsing alpha message from multimon-ng."""
        capture = PocsagCapture()
        line = "POCSAG512: Address: 1234567  Function: 0  Alpha: Hello World"
        msg = capture._parse_multimon_line(line)
        assert msg is not None
        assert msg.address == 1234567
        assert msg.function == 0
        assert msg.message_type == "alpha"
        assert msg.message == "Hello World"

    def test_parse_multimon_line_invalid(self) -> None:
        """Test parsing invalid line."""
        capture = PocsagCapture()
        line = "INVALID: some data"
        msg = capture._parse_multimon_line(line)
        assert msg is None

    @patch("neo_pocsag.pocsag.capture.RtlFmAudioCapture")
    @patch("neo_pocsag.pocsag.capture.subprocess.Popen")
    def test_capture_start_stop(self, mock_popen, mock_capture) -> None:
        """Test starting and stopping capture."""
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_popen.return_value = mock_proc

        capture = PocsagCapture()
        capture.start()
        assert capture.is_running()

        capture.stop()
        assert not capture.is_running()

    def test_get_stats(self) -> None:
        """Test getting capture statistics."""
        capture = PocsagCapture()
        stats = capture.get_stats()
        assert stats.total_messages == 0
        assert stats.unique_addresses == 0

    def test_start_already_running(self) -> None:
        """Test starting when already running."""
        capture = PocsagCapture()
        capture._running = True
        with patch("neo_pocsag.pocsag.capture.LOG") as mock_log:
            capture.start()
            mock_log.warning.assert_called_with("POCSAG capture already started")

    def test_stop_not_running(self) -> None:
        """Test stopping when not running."""
        capture = PocsagCapture()
        with patch("neo_pocsag.pocsag.capture.LOG") as mock_log:
            capture.stop()
            mock_log.warning.assert_called_with("POCSAG capture not running")

    def test_parse_multimon_line_numeric(self) -> None:
        """Test parsing numeric message."""
        capture = PocsagCapture()
        line = "POCSAG512: Address: 1234567  Function: 0  Numeric: 12345"
        msg = capture._parse_multimon_line(line)
        assert msg is not None
        assert msg.message_type == "numeric"
        assert msg.message == "12345"

    def test_parse_multimon_line_malformed(self) -> None:
        """Test parsing malformed line."""
        capture = PocsagCapture()
        line = "POCSAG512: Address: invalid  Function: 0  Alpha: test"
        msg = capture._parse_multimon_line(line)
        assert msg is None

    def test_handle_message_with_callback_error(self) -> None:
        """Test handling message with callback that raises exception."""
        capture = PocsagCapture()
        msg = PocsagMessage(address=1, function=0, message_type="alpha", message="test")
        
        def bad_callback(m):
            raise ValueError("test error")
        
        capture.add_callback(bad_callback)
        
        with patch("neo_pocsag.pocsag.capture.LOG") as mock_log:
            capture._handle_message(msg)
            mock_log.warning.assert_called_with("Callback error: %s", mock_log.warning.call_args[0][1])

    @patch("pathlib.Path.open")
    def test_log_message_oserror(self, mock_open) -> None:
        """Test logging message with file error."""
        mock_open.side_effect = OSError("disk full")
        capture = PocsagCapture()
        msg = PocsagMessage(address=1, function=0, message_type="alpha", message="test")
        
        with patch("neo_pocsag.pocsag.capture.LOG") as mock_log:
            capture._log_message(msg)
            mock_log.warning.assert_called_with("Failed to log message: %s", mock_log.warning.call_args[0][1])

    def test_publish_message_no_publisher(self) -> None:
        """Test publishing without publisher."""
        capture = PocsagCapture()
        msg = PocsagMessage(address=1, function=0, message_type="alpha", message="test")
        capture._publish_message(msg)  # Should not raise

    def test_publish_message_with_publisher_error(self) -> None:
        """Test publishing with publisher that raises exception."""
        capture = PocsagCapture()
        mock_publisher = Mock()
        mock_publisher.publish.side_effect = Exception("publish failed")
        capture._publisher = mock_publisher
        msg = PocsagMessage(address=1, function=0, message_type="alpha", message="test")
        
        with patch("neo_pocsag.pocsag.capture.LOG") as mock_log:
            capture._publish_message(msg)
            mock_log.warning.assert_called_with("Failed to publish message: %s", mock_log.warning.call_args[0][1])
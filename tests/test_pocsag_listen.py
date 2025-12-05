"""Tests for POCSAG listen command."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
from argparse import Namespace
from pathlib import Path

from neo_pocsag.commands.listen import run_listen


class TestPocsagListen:
    """Test POCSAG listen command."""

    @patch("neo_pocsag.commands.listen.config_module")
    @patch("neo_pocsag.pocsag.capture.PocsagCapture")
    @patch("neo_pocsag.commands.listen.start_keyboard_listener")
    def test_run_listen_basic(self, mock_kb, mock_capture_cls, mock_config) -> None:
        """Test basic listen command execution."""
        # Mock config
        mock_config.load_config.return_value = Mock()
        mock_config.load_config.return_value.mqtt_enabled = False
        mock_config.get_mode_data_dir.return_value = Mock()
        mock_config.get_logs_dir.return_value = Path("/tmp/logs")

        # Mock capture
        mock_capture = Mock()
        mock_capture.is_running.return_value = False
        mock_capture.get_stats.return_value = Mock(unique_addresses=0)
        mock_capture_cls.return_value = mock_capture

        # Mock keyboard
        mock_kb.return_value = Mock()

        args = Namespace(config=None, frequency=152840000, gain=None, ppm=0, device_index=0)

        # Run with timeout (since it's a loop)
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            result = run_listen(args)

        assert result == 0
        mock_capture.start.assert_called_once()
        mock_capture.stop.assert_called_once()

    @patch("neo_pocsag.commands.listen.config_module")
    @patch("neo_pocsag.pocsag.capture.PocsagCapture")
    @patch("neo_pocsag.commands.listen.start_keyboard_listener")
    def test_run_listen_with_config_frequency(self, mock_kb, mock_capture_cls, mock_config) -> None:
        """Test listen with frequency from config."""
        # Mock config
        mock_config.load_config.return_value = Mock()
        mock_config.load_config.return_value.pocsag_frequency_hz = 158100000
        mock_config.load_config.return_value.mqtt_enabled = False
        mock_config.get_mode_data_dir.return_value = Mock()
        mock_config.get_logs_dir.return_value = Path("/tmp/logs")

        # Mock capture
        mock_capture = Mock()
        mock_capture.is_running.return_value = False
        mock_capture.get_stats.return_value = Mock(unique_addresses=0)
        mock_capture_cls.return_value = mock_capture

        # Mock keyboard
        mock_kb.return_value = Mock()

        args = Namespace(config=None, frequency=None, gain=None, ppm=0, device_index=0)

        # Run with timeout
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            result = run_listen(args)

        assert result == 0
        # Should use config frequency
        mock_capture_cls.assert_called_once()
        call_args = mock_capture_cls.call_args
        assert call_args[1]['frequency_hz'] == 158100000

    @patch("neo_pocsag.commands.listen.config_module")
    @patch("neo_pocsag.pocsag.capture.PocsagCapture")
    @patch("neo_pocsag.commands.listen.start_keyboard_listener")
    @patch("neo_telemetry.mqtt_publisher.MqttPublisher")
    def test_run_listen_with_mqtt(self, mock_mqtt_cls, mock_kb, mock_capture_cls, mock_config) -> None:
        """Test listen with MQTT enabled."""
        # Mock config
        mock_config.load_config.return_value = Mock()
        mock_config.load_config.return_value.mqtt_enabled = True
        mock_config.load_config.return_value.mqtt_host = "localhost"
        mock_config.load_config.return_value.mqtt_port = 1883
        mock_config.get_mode_data_dir.return_value = Mock()
        mock_config.get_logs_dir.return_value = Path("/tmp/logs")

        # Mock MQTT
        mock_publisher = Mock()
        mock_mqtt_cls.return_value = mock_publisher

        # Mock capture
        mock_capture = Mock()
        mock_capture.is_running.return_value = False
        mock_capture.get_stats.return_value = Mock(unique_addresses=0)
        mock_capture_cls.return_value = mock_capture

        # Mock keyboard
        mock_kb.return_value = Mock()

        args = Namespace(config=None, frequency=152840000, gain=None, ppm=0, device_index=0)

        # Run with timeout
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            result = run_listen(args)

        assert result == 0
        mock_mqtt_cls.assert_called_once_with(host="localhost", port=1883)
        mock_publisher.connect.assert_called_once()
        mock_publisher.topic = "neo_rx/pocsag/messages"
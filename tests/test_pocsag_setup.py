"""Tests for POCSAG setup command."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
from argparse import Namespace
from pathlib import Path

from neo_pocsag.commands.setup import run_setup


class TestPocsagSetup:
    """Test POCSAG setup command."""

    @patch("neo_core.config.save_config")
    @patch("neo_core.config.load_config")
    @patch("neo_core.config.resolve_config_path")
    @patch("builtins.input")
    def test_run_setup_default_frequency(self, mock_input, mock_resolve, mock_load, mock_save) -> None:
        """Test setup with default frequency."""
        # Mock config path
        mock_resolve.return_value = Path("/tmp/config.toml")

        # Mock load config
        mock_config = Mock()
        mock_config.pocsag_frequency_hz = 152840000
        mock_load.return_value = mock_config

        # Mock input - empty for default
        mock_input.return_value = ""

        args = Namespace(config=None)

        result = run_setup(args)

        assert result == 0
        mock_save.assert_called_once_with(mock_config, Path("/tmp/config.toml"))

    @patch("neo_core.config.save_config")
    @patch("neo_core.config.load_config")
    @patch("neo_core.config.resolve_config_path")
    @patch("builtins.input")
    def test_run_setup_new_frequency(self, mock_input, mock_resolve, mock_load, mock_save) -> None:
        """Test setup with new frequency."""
        # Mock config path
        mock_resolve.return_value = Path("/tmp/config.toml")

        # Mock load config - return object without the attribute
        class Config:
            pass
        mock_config = Config()
        mock_load.return_value = mock_config

        # Mock input - new frequency
        mock_input.return_value = "158100000"

        args = Namespace(config=None)

        with patch("builtins.print"):  # Suppress print output
            result = run_setup(args)

        assert result == 0
        # Check that save_config was called with the new frequency
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert saved_config.pocsag_frequency_hz == 158100000
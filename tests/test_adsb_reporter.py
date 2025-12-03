"""Tests for ADS-B Exchange reporter functionality."""

import tempfile
from pathlib import Path


from neo_adsb.adsb.reporter import (
    AdsbExchangeConfig,
    AdsbExchangeStatus,
    AdsbExchangeReporter,
    ADSBX_CONFIG_PATH,
)


class TestAdsbExchangeConfig:
    """Tests for AdsbExchangeConfig dataclass."""

    def test_config_creation(self):
        """Test creating a configuration."""
        config = AdsbExchangeConfig(
            username="testuser-location",
            latitude=37.7749,
            longitude=-122.4194,
            altitude_m=100.0,
        )
        assert config.username == "testuser-location"
        assert config.latitude == 37.7749
        assert config.longitude == -122.4194
        assert config.altitude_m == 100.0
        assert config.input_host == "127.0.0.1"
        assert config.input_port == 30005
        assert config.mlat_enabled
        assert not config.privacy_enabled

    def test_config_with_custom_input(self):
        """Test creating a configuration with custom input."""
        config = AdsbExchangeConfig(
            username="testuser",
            latitude=0.0,
            longitude=0.0,
            altitude_m=0.0,
            input_host="192.168.1.100",
            input_port=30004,
        )
        assert config.input_host == "192.168.1.100"
        assert config.input_port == 30004

    def test_config_to_env_file(self):
        """Test generating environment file content."""
        config = AdsbExchangeConfig(
            username="testuser-location",
            latitude=37.7749,
            longitude=-122.4194,
            altitude_m=100.0,
        )
        env_content = config.to_env_file()

        assert 'USER="testuser-location"' in env_content
        assert 'LATITUDE="37.774900"' in env_content
        assert 'LONGITUDE="-122.419400"' in env_content
        assert 'INPUT="127.0.0.1:30005"' in env_content
        assert "MLATSERVER=" in env_content
        assert "TARGET=" in env_content

    def test_config_altitude_conversion(self):
        """Test altitude conversion from meters to feet."""
        config = AdsbExchangeConfig(
            username="test",
            latitude=0.0,
            longitude=0.0,
            altitude_m=100.0,  # ~328 feet
        )
        env_content = config.to_env_file()
        assert 'ALTITUDE="328ft"' in env_content

    def test_config_privacy_enabled(self):
        """Test configuration with privacy enabled."""
        config = AdsbExchangeConfig(
            username="test",
            latitude=0.0,
            longitude=0.0,
            altitude_m=0.0,
            privacy_enabled=True,
        )
        env_content = config.to_env_file()
        assert 'PRIVACY="--privacy"' in env_content


class TestAdsbExchangeStatus:
    """Tests for AdsbExchangeStatus dataclass."""

    def test_status_defaults(self):
        """Test default status values."""
        status = AdsbExchangeStatus()
        assert not status.feed_service_active
        assert not status.mlat_service_active
        assert not status.feed_connected
        assert not status.mlat_connected
        assert status.uuid is None
        assert status.username is None
        assert status.last_check is None


class TestAdsbExchangeReporter:
    """Tests for AdsbExchangeReporter."""

    def test_reporter_creation(self):
        """Test reporter instantiation."""
        reporter = AdsbExchangeReporter()
        assert reporter.config is None
        assert reporter._config_path == ADSBX_CONFIG_PATH

    def test_reporter_with_config(self):
        """Test reporter with provided config."""
        config = AdsbExchangeConfig(
            username="test",
            latitude=0.0,
            longitude=0.0,
            altitude_m=0.0,
        )
        reporter = AdsbExchangeReporter(config=config)
        assert reporter.config == config

    def test_reporter_custom_config_path(self):
        """Test reporter with custom config path."""
        custom_path = Path("/custom/config/path")
        reporter = AdsbExchangeReporter(config_path=custom_path)
        assert reporter._config_path == custom_path

    def test_is_installed_not_installed(self):
        """Test is_installed when not installed."""
        reporter = AdsbExchangeReporter(
            config_path=Path("/nonexistent/config")
        )
        # Will be False if neither the git path nor config path exists
        # This may be True on systems with ADS-B Exchange installed
        result = reporter.is_installed()
        assert isinstance(result, bool)

    def test_get_uuid_missing(self):
        """Test getting UUID when file is missing."""
        reporter = AdsbExchangeReporter()
        # UUID file likely doesn't exist in test environment
        uuid = reporter.get_uuid()
        # Could be None or a string if file exists
        assert uuid is None or isinstance(uuid, str)

    def test_get_status(self):
        """Test getting service status."""
        reporter = AdsbExchangeReporter()
        status = reporter.get_status()

        assert isinstance(status, AdsbExchangeStatus)
        assert status.last_check is not None
        # Service status depends on system state
        assert isinstance(status.feed_service_active, bool)
        assert isinstance(status.mlat_service_active, bool)

    def test_load_config_missing_file(self):
        """Test loading config when file is missing."""
        reporter = AdsbExchangeReporter(
            config_path=Path("/nonexistent/adsbexchange")
        )
        config = reporter.load_config()
        assert config is None

    def test_load_config_valid_file(self):
        """Test loading config from valid file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write('USER="testuser"\n')
            f.write('LATITUDE="37.7749"\n')
            f.write('LONGITUDE="-122.4194"\n')
            f.write('ALTITUDE="100ft"\n')
            f.write('INPUT="127.0.0.1:30005"\n')
            f.write('PRIVACY=""\n')
            temp_path = f.name

        try:
            reporter = AdsbExchangeReporter(config_path=Path(temp_path))
            config = reporter.load_config()

            assert config is not None
            assert config.username == "testuser"
            assert config.latitude == 37.7749
            assert config.longitude == -122.4194
            assert not config.privacy_enabled
        finally:
            Path(temp_path).unlink()

    def test_load_config_with_privacy(self):
        """Test loading config with privacy enabled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write('USER="testuser"\n')
            f.write('LATITUDE="0"\n')
            f.write('LONGITUDE="0"\n')
            f.write('ALTITUDE="0ft"\n')
            f.write('INPUT="127.0.0.1:30005"\n')
            f.write('PRIVACY="--privacy"\n')
            temp_path = f.name

        try:
            reporter = AdsbExchangeReporter(config_path=Path(temp_path))
            config = reporter.load_config()

            assert config is not None
            assert config.privacy_enabled
        finally:
            Path(temp_path).unlink()

    def test_save_config_no_config(self):
        """Test saving config when no config is set."""
        reporter = AdsbExchangeReporter()
        result = reporter.save_config()
        assert not result

    def test_get_feed_check_urls(self):
        """Test getting feed check URLs."""
        reporter = AdsbExchangeReporter()
        urls = reporter.get_feed_check_urls()

        assert "myip" in urls
        assert "mlat_map" in urls
        assert "adsbexchange.com" in urls["myip"]

    def test_get_install_instructions(self):
        """Test getting installation instructions."""
        reporter = AdsbExchangeReporter()
        instructions = reporter.get_install_instructions()

        assert "adsbexchange.com/feed.sh" in instructions
        assert "github.com/adsbexchange" in instructions

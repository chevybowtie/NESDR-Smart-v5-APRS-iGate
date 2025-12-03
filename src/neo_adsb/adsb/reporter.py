"""ADS-B Exchange reporter integration.

This module provides optional reporting to ADS-B Exchange network.
It integrates with the ADS-B Exchange feedclient infrastructure.

For full ADS-B Exchange integration, users should install the official
feedclient from: https://github.com/adsbexchange/feedclient

This reporter provides status monitoring and configuration helpers.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)

# Default ADS-B Exchange configuration paths
ADSBX_CONFIG_PATH = Path("/etc/default/adsbexchange")
ADSBX_UUID_PATH = Path("/usr/local/share/adsbexchange/adsbx-uuid")
ADSBX_GIT_PATH = Path("/usr/local/share/adsbexchange/git")


@dataclass
class AdsbExchangeConfig:
    """Configuration for ADS-B Exchange reporting."""

    username: str
    latitude: float
    longitude: float
    altitude_m: float
    input_host: str = "127.0.0.1"
    input_port: int = 30005
    uuid: str | None = None
    mlat_enabled: bool = True
    privacy_enabled: bool = False

    def to_env_file(self) -> str:
        """Generate /etc/default/adsbexchange format configuration."""
        altitude_ft = int(self.altitude_m * 3.28084)
        lines = [
            f'INPUT="{self.input_host}:{self.input_port}"',
            'REDUCE_INTERVAL="0.5"',
            f'USER="{self.username}"',
            f'LATITUDE="{self.latitude:.6f}"',
            f'LONGITUDE="{self.longitude:.6f}"',
            f'ALTITUDE="{altitude_ft}ft"',
            'UAT_INPUT="127.0.0.1:30978"',
            'RESULTS="--results beast,connect,127.0.0.1:30104"',
            'RESULTS2="--results basestation,listen,31003"',
            'RESULTS3="--results beast,listen,30157"',
            'RESULTS4="--results beast,connect,127.0.0.1:30154"',
            f'PRIVACY="{("--privacy" if self.privacy_enabled else "")}"',
            'INPUT_TYPE="dump1090"',
            'MLATSERVER="feed.adsbexchange.com:31090"',
            'TARGET="--net-connector feed1.adsbexchange.com,30004,beast_reduce_out,feed2.adsbexchange.com,64004"',
            'NET_OPTIONS="--net-heartbeat 60 --net-ro-size 1280 --net-ro-interval 0.2 --net-ro-port 0 --net-sbs-port 0 --net-bi-port 30154 --net-bo-port 0 --net-ri-port 0 --write-json-every 1"',
            'JSON_OPTIONS="--max-range 450 --json-location-accuracy 2 --range-outline-hours 24"',
        ]
        return "\n".join(lines) + "\n"


@dataclass
class AdsbExchangeStatus:
    """Status of ADS-B Exchange services."""

    feed_service_active: bool = False
    mlat_service_active: bool = False
    feed_connected: bool = False
    mlat_connected: bool = False
    uuid: str | None = None
    username: str | None = None
    last_check: datetime | None = None


class AdsbExchangeReporter:
    """Integration with ADS-B Exchange feed infrastructure.

    This class provides:
    - Status monitoring of ADS-B Exchange services
    - Configuration file generation
    - Service health checks

    Note: Actual data feeding is handled by the official adsbexchange-feed
    service which should be installed separately.
    """

    def __init__(
        self,
        config: AdsbExchangeConfig | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._config = config
        self._config_path = config_path or ADSBX_CONFIG_PATH
        self._status = AdsbExchangeStatus()

    @property
    def config(self) -> AdsbExchangeConfig | None:
        """Return the current configuration."""
        return self._config

    def is_installed(self) -> bool:
        """Check if ADS-B Exchange feedclient is installed."""
        return ADSBX_GIT_PATH.exists() or self._config_path.exists()

    def get_uuid(self) -> str | None:
        """Read the ADS-B Exchange feeder UUID if available."""
        if ADSBX_UUID_PATH.exists():
            try:
                return ADSBX_UUID_PATH.read_text().strip()
            except OSError:
                pass
        return None

    def get_status(self) -> AdsbExchangeStatus:
        """Check the status of ADS-B Exchange services.

        This checks:
        - Whether the feed service is running
        - Whether the MLAT service is running
        - Current configuration
        """
        status = AdsbExchangeStatus(last_check=datetime.now(timezone.utc))

        # Check feed service status
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "adsbexchange-feed"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status.feed_service_active = result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            status.feed_service_active = False

        # Check MLAT service status
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "adsbexchange-mlat"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status.mlat_service_active = result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            status.mlat_service_active = False

        # Read UUID and username from config
        status.uuid = self.get_uuid()
        if self._config_path.exists():
            try:
                config_text = self._config_path.read_text()
                for line in config_text.splitlines():
                    if line.startswith("USER="):
                        status.username = line.split("=", 1)[1].strip('"')
                        break
            except OSError:
                pass

        self._status = status
        return status

    def load_config(self) -> AdsbExchangeConfig | None:
        """Load existing configuration from /etc/default/adsbexchange."""
        if not self._config_path.exists():
            return None

        try:
            config_text = self._config_path.read_text()
            values: dict[str, str] = {}
            for line in config_text.splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"')

            # Parse input host:port
            input_parts = values.get("INPUT", "127.0.0.1:30005").split(":")
            input_host = input_parts[0] if len(input_parts) >= 1 else "127.0.0.1"
            input_port = int(input_parts[1]) if len(input_parts) >= 2 else 30005

            # Parse altitude (convert from ft to m if needed)
            altitude_str = values.get("ALTITUDE", "0ft")
            if altitude_str.endswith("ft"):
                altitude_m = float(altitude_str[:-2]) / 3.28084
            elif altitude_str.endswith("m"):
                altitude_m = float(altitude_str[:-1])
            else:
                altitude_m = float(altitude_str)

            self._config = AdsbExchangeConfig(
                username=values.get("USER", ""),
                latitude=float(values.get("LATITUDE", "0")),
                longitude=float(values.get("LONGITUDE", "0")),
                altitude_m=altitude_m,
                input_host=input_host,
                input_port=input_port,
                privacy_enabled="--privacy" in values.get("PRIVACY", ""),
            )
            self._config.uuid = self.get_uuid()
            return self._config
        except (OSError, ValueError) as exc:
            LOG.warning("Failed to load ADS-B Exchange config: %s", exc)
            return None

    def save_config(self, config: AdsbExchangeConfig | None = None) -> bool:
        """Save configuration to /etc/default/adsbexchange.

        Requires root privileges. Returns True on success.
        """
        cfg = config or self._config
        if cfg is None:
            LOG.error("No configuration to save")
            return False

        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(cfg.to_env_file())
            LOG.info("Saved ADS-B Exchange configuration to %s", self._config_path)
            return True
        except OSError as exc:
            LOG.error("Failed to save ADS-B Exchange config: %s", exc)
            return False

    def restart_services(self) -> bool:
        """Restart ADS-B Exchange services.

        Requires root privileges. Returns True on success.
        """
        try:
            subprocess.run(
                ["systemctl", "restart", "adsbexchange-feed"],
                check=True,
                timeout=30,
            )
            subprocess.run(
                ["systemctl", "restart", "adsbexchange-mlat"],
                check=True,
                timeout=30,
            )
            LOG.info("Restarted ADS-B Exchange services")
            return True
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            LOG.error("Failed to restart ADS-B Exchange services: %s", exc)
            return False

    def get_feed_check_urls(self) -> dict[str, str]:
        """Return URLs for checking feed status."""
        return {
            "myip": "https://www.adsbexchange.com/myip",
            "mlat_map": "https://map.adsbexchange.com/mlat-map",
        }

    def get_install_instructions(self) -> str:
        """Return installation instructions for ADS-B Exchange feedclient."""
        return """To install the ADS-B Exchange feed client:

1. Install the feed client:
   curl -L -o /tmp/axfeed.sh https://adsbexchange.com/feed.sh
   sudo bash /tmp/axfeed.sh

2. Check your feed is working:
   https://www.adsbexchange.com/myip
   https://map.adsbexchange.com/mlat-map

3. Optional: Install stats package for local map:
   curl -L -o /tmp/axstats.sh https://adsbexchange.com/stats.sh
   sudo bash /tmp/axstats.sh

For more information:
https://github.com/adsbexchange/feedclient
"""

"""Configuration loading and persistence helpers."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli_w  # type: ignore[import]

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore[no-redef]

try:  # Optional dependency for secure credential storage
    import keyring as _keyring  # type: ignore[import]
    from keyring.errors import KeyringError  # type: ignore[import]
except ImportError:  # pragma: no cover - keyring not installed
    _keyring = None
    KeyringError = Exception

CONFIG_VERSION = 1
CONFIG_ENV_VAR = "NESDR_IGATE_CONFIG_PATH"
CONFIG_DIR_NAME = "nesdr-igate"
CONFIG_FILENAME = "config.toml"
KEYRING_SERVICE = "nesdr-igate"
KEYRING_SENTINEL = "__KEYRING__"


def _xdg_path(env_var: str, default: Path) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value).expanduser()
    return default


def get_config_dir() -> Path:
    """Return the directory containing configuration files."""
    default = Path.home() / ".config"
    return _xdg_path("XDG_CONFIG_HOME", default) / CONFIG_DIR_NAME


def get_data_dir() -> Path:
    """Return the directory for runtime data/log files."""
    default = Path.home() / ".local" / "share"
    return _xdg_path("XDG_DATA_HOME", default) / CONFIG_DIR_NAME


def resolve_config_path(path: str | Path | None = None) -> Path:
    """Resolve the configuration file path, honouring overrides."""
    if path is not None:
        return Path(path).expanduser()
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()
    return get_config_dir() / CONFIG_FILENAME


@dataclass(slots=True)
class StationConfig:
    """Contains station identity, APRS-IS credentials, and radio defaults."""

    callsign: str
    passcode: str
    passcode_in_keyring: bool = False
    aprs_server: str = "noam.aprs2.net"
    aprs_port: int = 14580
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    beacon_comment: str | None = None
    software_tocall: str | None = None
    kiss_host: str = "127.0.0.1"
    kiss_port: int = 8001
    center_frequency_hz: float = 144_390_000.0
    sample_rate_sps: float = 250_000.0
    gain: float | str | None = None
    ppm_correction: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the configuration to a TOML-serialisable dictionary."""
        return {
            "version": CONFIG_VERSION,
            "station": _drop_none(
                {
                    "callsign": self.callsign,
                    "passcode": KEYRING_SENTINEL
                    if self.passcode_in_keyring
                    else self.passcode,
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "altitude_m": self.altitude_m,
                    "beacon_comment": self.beacon_comment,
                    "software_tocall": self.software_tocall,
                }
            ),
            "aprs": _drop_none(
                {
                    "server": self.aprs_server,
                    "port": self.aprs_port,
                }
            ),
            "radio": _drop_none(
                {
                    "center_frequency_hz": self.center_frequency_hz,
                    "sample_rate_sps": self.sample_rate_sps,
                    "gain": self.gain,
                    "ppm_correction": self.ppm_correction,
                }
            ),
            "direwolf": _drop_none(
                {
                    "kiss_host": self.kiss_host,
                    "kiss_port": self.kiss_port,
                }
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StationConfig:
        """Construct from a dictionary (typically parsed from TOML)."""
        version = data.get("version", 1)
        if version != CONFIG_VERSION:
            raise ValueError(f"Unsupported config version: {version}")

        station = data.get("station", {})
        aprs = data.get("aprs", {})
        radio = data.get("radio", {})
        direwolf = data.get("direwolf", {})

        callsign = station.get("callsign")
        passcode = station.get("passcode")
        if not callsign or not passcode:
            raise ValueError("Configuration missing required callsign/passcode")

        passcode_in_keyring = False
        if isinstance(passcode, str) and passcode == KEYRING_SENTINEL:
            passcode = _retrieve_passcode_from_keyring(str(callsign))
            passcode_in_keyring = True

        return cls(
            callsign=str(callsign),
            passcode=str(passcode),
            passcode_in_keyring=passcode_in_keyring,
            aprs_server=str(aprs.get("server", "noam.aprs2.net")),
            aprs_port=int(aprs.get("port", 14580)),
            latitude=_optional_float(station.get("latitude")),
            longitude=_optional_float(station.get("longitude")),
            altitude_m=_optional_float(station.get("altitude_m")),
            beacon_comment=station.get("beacon_comment"),
            software_tocall=station.get("software_tocall"),
            kiss_host=str(direwolf.get("kiss_host", "127.0.0.1")),
            kiss_port=int(direwolf.get("kiss_port", 8001)),
            center_frequency_hz=float(radio.get("center_frequency_hz", 144_390_000.0)),
            sample_rate_sps=float(radio.get("sample_rate_sps", 250_000.0)),
            gain=radio.get("gain"),
            ppm_correction=_optional_int(radio.get("ppm_correction")),
        )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _drop_none(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def load_config(path: str | Path | None = None) -> StationConfig:
    """Load persisted configuration."""
    config_path = resolve_config_path(path)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    return StationConfig.from_dict(data)


def save_config(config: StationConfig, path: str | Path | None = None) -> Path:
    """Persist configuration to disk and return the file path."""
    if config.passcode_in_keyring:
        _store_passcode_in_keyring(config.callsign, config.passcode)
    config_path = resolve_config_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    toml_text = tomli_w.dumps(config.to_dict())
    config_path.write_text(toml_text, encoding="utf-8")
    try:
        os.chmod(config_path, stat.S_IRUSR | stat.S_IWUSR)
    except PermissionError:  # pragma: no cover - some FS disallow chmod
        pass
    return config_path


def config_summary(config: StationConfig) -> str:
    """Generate a human-readable summary of key settings."""
    location = "not set"
    if config.latitude is not None and config.longitude is not None:
        location = f"{config.latitude:.4f}, {config.longitude:.4f}"
    return (
        f"  Callsign : {config.callsign}\n"
        f"  APRS-IS : {config.aprs_server}:{config.aprs_port}\n"
        f"  Location : {location}\n"
        f"  KISS     : {config.kiss_host}:{config.kiss_port}\n"
        f"  Radio    : {config.center_frequency_hz / 1e6:.3f} MHz @ {config.sample_rate_sps:.0f} sps"
    )


def keyring_supported() -> bool:
    """Return True if a keyring backend is available."""
    return _keyring is not None


def store_passcode_in_keyring(callsign: str, passcode: str) -> None:
    """Persist the APRS-IS passcode in the system keyring."""
    _store_passcode_in_keyring(callsign, passcode)


def delete_passcode_from_keyring(callsign: str) -> None:
    """Remove the APRS-IS passcode from the system keyring if present."""
    if _keyring is None:
        return
    try:
        _keyring.delete_password(KEYRING_SERVICE, callsign)
    except KeyringError:  # pragma: no cover - backend quirks
        pass


def _store_passcode_in_keyring(callsign: str, passcode: str) -> None:
    if _keyring is None:
        raise ValueError("Keyring backend not available; install 'keyring' package")
    try:
        _keyring.set_password(KEYRING_SERVICE, callsign, passcode)
    except KeyringError as exc:  # pragma: no cover - backend dependent
        raise ValueError(f"Failed to store passcode in keyring: {exc}") from exc


def _retrieve_passcode_from_keyring(callsign: str) -> str:
    if _keyring is None:
        raise ValueError("Keyring backend not available for stored passcode")
    try:
        value = _keyring.get_password(KEYRING_SERVICE, callsign)
    except KeyringError as exc:  # pragma: no cover - backend dependent
        raise ValueError(f"Failed to read passcode from keyring: {exc}") from exc
    if not value:
        raise ValueError("No APRS-IS passcode stored in keyring; rerun setup")
    return value

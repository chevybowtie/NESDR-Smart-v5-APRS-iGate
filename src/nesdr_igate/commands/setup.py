"""Onboarding command implementation."""

from __future__ import annotations

import importlib.resources as resources
import os
import re
from argparse import Namespace
from getpass import getpass
from pathlib import Path
from typing import Callable

from nesdr_igate import config as config_module
from nesdr_igate.config import StationConfig

CALLSIGN_PATTERN = re.compile(r"^[A-Z0-9]{1,6}-[0-9]{1,2}$")


def run_setup(args: Namespace) -> int:
    """Run the onboarding workflow."""
    config_path = config_module.resolve_config_path(args.config)

    if args.reset and config_path.exists():
        config_path.unlink()
        print(f"Removed existing configuration at {config_path}")

    if args.non_interactive:
        return _run_non_interactive(config_path)

    try:
        existing = _load_existing(config_path)
    except ValueError as exc:
        print(f"Warning: existing configuration invalid ({exc}); starting fresh")
        existing = None

    try:
        new_config = _interactive_prompt(existing)
    except KeyboardInterrupt:
        print("\nSetup cancelled by user")
        return 1

    if args.dry_run:
        print("Dry run: configuration not written")
        print(config_module.config_summary(new_config))
        return 0

    saved_path = config_module.save_config(new_config, path=config_path)
    print(f"Configuration saved to {saved_path}")
    print(config_module.config_summary(new_config))
    _maybe_render_direwolf_config(new_config, saved_path.parent)
    return 0


def _run_non_interactive(config_path: Path) -> int:
    try:
        config = config_module.load_config(config_path)
    except FileNotFoundError:
        print(f"Configuration not found at {config_path}; run interactive setup first")
        return 1
    except ValueError as exc:
        print(f"Configuration invalid: {exc}")
        return 1

    print("Configuration OK:")
    print(config_module.config_summary(config))
    return 0


def _load_existing(config_path: Path) -> StationConfig | None:
    if not config_path.exists():
        return None
    try:
        return config_module.load_config(config_path)
    except (FileNotFoundError, ValueError):
        return None


def _interactive_prompt(existing: StationConfig | None) -> StationConfig:
    prompt = _Prompt(existing)

    callsign = prompt.string(
        "APRS callsign-SSID", default=_default(existing, "callsign"), transform=str.upper, validator=_validate_callsign
    )
    passcode = prompt.secret(
        "APRS-IS passcode",
        default=_default(existing, "passcode"),
    )
    aprs_server = prompt.string(
        "APRS-IS server",
        default=_default(existing, "aprs_server", fallback="noam.aprs2.net"),
    )
    aprs_port = prompt.integer(
        "APRS-IS port",
        default=_default(existing, "aprs_port", fallback=14580),
        minimum=1,
        maximum=65535,
    )
    latitude = prompt.optional_float(
        "Station latitude",
        default=_default(existing, "latitude"),
    )
    longitude = prompt.optional_float(
        "Station longitude",
        default=_default(existing, "longitude"),
    )
    beacon_comment = prompt.optional_string(
        "Beacon comment",
        default=_default(existing, "beacon_comment"),
    )

    kiss_host = prompt.string(
        "Direwolf KISS host",
        default=_default(existing, "kiss_host", fallback="127.0.0.1"),
    )
    kiss_port = prompt.integer(
        "Direwolf KISS port",
        default=_default(existing, "kiss_port", fallback=8001),
        minimum=1,
        maximum=65535,
    )

    return StationConfig(
        callsign=callsign,
        passcode=passcode,
        aprs_server=aprs_server,
        aprs_port=aprs_port,
        latitude=latitude,
        longitude=longitude,
        beacon_comment=beacon_comment,
        kiss_host=kiss_host,
        kiss_port=kiss_port,
    )


def _default(config: StationConfig | None, attr: str, fallback: object | None = None) -> object | None:
    if config is None:
        return fallback
    return getattr(config, attr)


def _validate_callsign(value: str) -> None:
    if not CALLSIGN_PATTERN.match(value):
        raise ValueError("Enter callsign-SSID like N0CALL-10")


class _Prompt:
    """Utility helpers for prompting user input with validation."""

    def __init__(self, existing: StationConfig | None) -> None:
        self._existing = existing

    def string(
        self,
        label: str,
        default: object | None = None,
        *,
        transform: Callable[[str], str] | None = None,
        validator: Callable[[str], None] | None = None,
    ) -> str:
        while True:
            prompt = _format_prompt(label, default)
            raw = input(prompt).strip()
            if not raw and default is not None:
                value = str(default)
            else:
                value = raw
            if not value:
                print("Value required")
                continue
            if transform is not None:
                value = transform(value)
            if validator is not None:
                try:
                    validator(value)
                except ValueError as exc:
                    print(exc)
                    continue
            return value

    def optional_string(self, label: str, default: object | None = None) -> str | None:
        prompt = _format_prompt(label, default)
        raw = input(prompt).strip()
        if not raw:
            return None if default is None else str(default)
        return raw

    def integer(
        self,
        label: str,
        default: object | None = None,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        while True:
            prompt = _format_prompt(label, default)
            raw = input(prompt).strip()
            if not raw and default is not None:
                value = _parse_int(default)
            else:
                value = _parse_int(raw)
            if value is None:
                print("Enter a valid integer")
                continue
            if minimum is not None and value < minimum:
                print(f"Value must be >= {minimum}")
                continue
            if maximum is not None and value > maximum:
                print(f"Value must be <= {maximum}")
                continue
            return value

    def optional_float(self, label: str, default: object | None = None) -> float | None:
        while True:
            prompt = _format_prompt(label, default)
            raw = input(prompt).strip()
            if not raw:
                return None if default is None else _parse_float(default)
            parsed = _parse_float(raw)
            if parsed is None:
                print("Enter a numeric value or leave blank")
                continue
            return parsed

    def secret(self, label: str, default: object | None = None) -> str:
        while True:
            if default is not None:
                prompt = f"{label} [leave blank to keep existing]: "
            else:
                prompt = f"{label}: "
            value = getpass(prompt)
            if not value and default is not None:
                return str(default)
            if not value:
                print("Value required")
                continue
            confirm = getpass("Confirm passcode: ")
            if value != confirm:
                print("Passcodes do not match; try again")
                continue
            return value


def _format_prompt(label: str, default: object | None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    return f"{label}{suffix}: "


def _parse_int(raw: object) -> int | None:
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_float(raw: object) -> float | None:
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _maybe_render_direwolf_config(config: StationConfig, target_dir: Path) -> None:
    template = _load_direwolf_template()
    if template is None:
        print("Direwolf template unavailable; skipping auto-render")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / "direwolf.conf"

    if dest_path.exists():
        message = f"Overwrite existing Direwolf config at {dest_path}?"
        proceed = _prompt_yes_no(message, default=False)
        if not proceed:
            print("Keeping existing Direwolf configuration")
            return
    else:
        message = f"Create Direwolf config at {dest_path}?"
        proceed = _prompt_yes_no(message, default=True)
        if not proceed:
            print("Skipping Direwolf configuration rendering")
            return

    log_dir = config_module.get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    replacements = {
        "AUDIO_SAMPLE_RATE": "22050",
        "CALLSIGN": config.callsign,
        "PASSCODE": config.passcode,
        "IGSERVER": f"{config.aprs_server} {config.aprs_port}",
        "LATITUDE": _format_coordinate(config.latitude, fallback="REPLACE_LAT"),
        "LONGITUDE": _format_coordinate(config.longitude, fallback="REPLACE_LON"),
        "BEACON_COMMENT": _escape_comment(
            config.beacon_comment or f"{config.callsign} NESDR iGate"
        ),
        "KISSPORT": str(config.kiss_port),
        "LOGDIR": str(log_dir),
    }

    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(f"{{{{{placeholder}}}}}", value)

    dest_path.write_text(rendered, encoding="utf-8")
    try:
        os.chmod(dest_path, 0o600)
    except PermissionError:  # pragma: no cover - some FS disallow chmod
        pass

    print(f"Direwolf configuration written to {dest_path}")


def _load_direwolf_template() -> str | None:
    try:
        return resources.files("nesdr_igate.templates").joinpath("direwolf.conf").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):  # pragma: no cover - defensive
        return None


def _format_coordinate(value: float | None, *, fallback: str) -> str:
    if value is None:
        return fallback
    return f"{value:.6f}"


def _escape_comment(comment: str) -> str:
    return comment.replace("\"", "\\\"")


def _prompt_yes_no(message: str, *, default: bool) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        response = input(f"{message}{suffix}: ").strip().lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please answer 'y' or 'n'")

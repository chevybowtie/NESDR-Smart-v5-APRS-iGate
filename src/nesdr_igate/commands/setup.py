"""Onboarding command implementation."""

from __future__ import annotations

import importlib.resources as resources
import os
import re
import shutil
import subprocess
from argparse import Namespace
from collections import deque
from getpass import getpass
from pathlib import Path

from importlib import import_module
from typing import TYPE_CHECKING, Any, Callable, Type

if TYPE_CHECKING:  # pragma: no cover - type checking only
    PromptSession: Type[Any]
    prompt_yes_no: Callable[..., bool]
else:
    _setup_io = import_module("nesdr_igate.commands.setup_io")
    PromptSession = _setup_io.PromptSession
    prompt_yes_no = _setup_io.prompt_yes_no

from nesdr_igate import config as config_module
from nesdr_igate.config import StationConfig
from nesdr_igate.diagnostics_helpers import probe_tcp_endpoint

CALLSIGN_PATTERN = re.compile(r"^[A-Z0-9]{1,6}-[0-9]{1,2}$")


def run_setup(args: Namespace) -> int:
    """Run the onboarding workflow."""
    config_path = config_module.resolve_config_path(args.config)

    if args.reset:
        try:
            existing_config = config_module.load_config(config_path)
        except FileNotFoundError:
            existing_config = None
        except Exception:  # pragma: no cover - best effort cleanup
            existing_config = None
        if existing_config and existing_config.passcode_in_keyring:
            config_module.delete_passcode_from_keyring(existing_config.callsign)
        removed = config_path.exists()
        config_path.unlink(missing_ok=True)
        if removed:
            print(f"Removed existing configuration at {config_path}")

    if args.non_interactive:
        return _run_non_interactive(config_path)

    existing, load_error = _load_existing(config_path)
    if load_error is not None and load_error != _MISSING_CONFIG_SENTINEL:
        print(f"Warning: existing configuration invalid ({load_error}); starting fresh")
        existing = None
    elif load_error == _MISSING_CONFIG_SENTINEL:
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
    config_dir = saved_path.parent
    _maybe_render_direwolf_config(new_config, config_dir)
    _offer_hardware_validation(new_config, config_dir)
    return 0


def _run_non_interactive(config_path: Path) -> int:
    """Validate an existing config file without prompting the user."""

    config, load_error = _load_existing(config_path)
    if config is None:
        if load_error == _MISSING_CONFIG_SENTINEL:
            print(f"Configuration not found at {config_path}; run interactive setup first")
        else:
            print(f"Configuration invalid: {load_error}")
        return 1

    print("Configuration OK:")
    print(config_module.config_summary(config))
    return 0


_MISSING_CONFIG_SENTINEL = "missing"


def _load_existing(config_path: Path) -> tuple[StationConfig | None, str | None]:
    """Return a previously saved configuration and any load error string."""

    if not config_path.exists():
        return None, _MISSING_CONFIG_SENTINEL
    try:
        return config_module.load_config(config_path), None
    except ValueError as exc:
        return None, str(exc)


def _interactive_prompt(existing: StationConfig | None) -> StationConfig:
    """Collect station details from stdin, seeding defaults from an existing config."""

    session = PromptSession(existing, secret_func=getpass)
    prompt = session.prompt

    callsign = prompt.string(
        "APRS callsign-SSID", default=_default(existing, "callsign"), transform=str.upper, validator=_validate_callsign
    )
    passcode = prompt.secret(
        "APRS-IS passcode",
        default=_default(existing, "passcode"),
    )
    use_keyring = bool(getattr(existing, "passcode_in_keyring", False))
    if config_module.keyring_supported():
        store_choice = session.ask_yes_no(
            "Store APRS-IS passcode in system keyring?",
            default=use_keyring,
        )
        if store_choice:
            try:
                config_module.store_passcode_in_keyring(callsign, passcode)
                use_keyring = True
            except ValueError as exc:
                print(f"Keyring unavailable: {exc}")
                use_keyring = False
        else:
            if use_keyring:
                config_module.delete_passcode_from_keyring(callsign)
            use_keyring = False
    elif use_keyring:
        print(
            "Warning: existing configuration referenced keyring-stored passcode, "
            "but keyring backend is unavailable. Keeping passcode in config file."
        )
        use_keyring = False

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
        passcode_in_keyring=use_keyring,
        aprs_server=aprs_server,
        aprs_port=aprs_port,
        latitude=latitude,
        longitude=longitude,
        beacon_comment=beacon_comment,
        kiss_host=kiss_host,
        kiss_port=kiss_port,
    )


def _default(config: StationConfig | None, attr: str, fallback: object | None = None) -> object | None:
    """Return attribute value from config if present, else fallback."""

    if config is None:
        return fallback
    return getattr(config, attr)


def _validate_callsign(value: str) -> None:
    """Ensure a callsign-SSID matches standard APRS formatting."""

    if not CALLSIGN_PATTERN.match(value):
        raise ValueError("Enter callsign-SSID like N0CALL-10")


def _maybe_render_direwolf_config(config: StationConfig, target_dir: Path) -> None:
    """Render a direwolf.conf file based on the template and station config."""

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
    """Load the direwolf configuration template text from package data."""

    try:
        return resources.files("nesdr_igate.templates").joinpath("direwolf.conf").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):  # pragma: no cover - defensive
        return None


def _format_coordinate(value: float | None, *, fallback: str) -> str:
    """Render a coordinate value or return a placeholder fallback."""

    if value is None:
        return fallback
    return f"{value:.6f}"


def _escape_comment(comment: str) -> str:
    """Escape double quotes in the beacon comment for Direwolf syntax."""

    return comment.replace("\"", "\\\"")


def _prompt_yes_no(message: str, *, default: bool) -> bool:
    """Backward-compatible wrapper around shared yes/no prompt helper."""

    return prompt_yes_no(message, default=default)


def _offer_hardware_validation(config: StationConfig, config_dir: Path | None = None) -> None:
    """Optionally kick off the post-setup hardware validation flow.

    Args:
        config: The station configuration to validate.
        config_dir: Directory containing generated configuration files, if known.
    """

    message = "Run a quick SDR/Direwolf validation now?"
    if not _prompt_yes_no(message, default=False):
        return
    _run_hardware_validation(config, config_dir)


_COMMAND_CHECKS: list[tuple[str, str]] = [
    ("rtl_fm", "RTL-SDR capture utility"),
    ("rtl_test", "RTL-SDR self-test"),
    ("direwolf", "Direwolf modem"),
]


def _run_hardware_validation(config: StationConfig, config_dir: Path | None = None) -> None:
    """Execute a series of checks to validate SDR and Direwolf readiness.

    Args:
        config: The station configuration under validation.
        config_dir: Preferred directory for Direwolf assets created during setup.
    """

    print("\nRunning hardware validation...")

    _report_command_availability()
    ppm_hint = _measure_rtl_ppm_offset()
    _report_connectivity(config)
    _report_direwolf_log_summary()
    _prompt_launch_direwolf_probe(config, config_dir)
    _print_ppm_tip(ppm_hint)

    print("Hardware validation complete. Review warnings above for follow-up.")


def _report_command_availability() -> None:
    """Emit status lines for essential external commands."""

    for command, description in _COMMAND_CHECKS:
        path = shutil.which(command)
        if path:
            print(f"[OK     ] {command}: found ({description})")
        else:
            print(f"[WARNING] {command}: not found in PATH ({description})")


def _measure_rtl_ppm_offset() -> str | None:
    """Run rtl_test to estimate ppm offset, returning the parsed hint if available."""

    if shutil.which("rtl_test") is None:
        return None

    try:
        proc = subprocess.run(
            ["rtl_test", "-p", "-d", "0"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("[WARNING] rtl_test: timed out (ensure the SDR is connected)")
        return None
    except OSError as exc:
        print(f"[WARNING] rtl_test: failed to execute ({exc})")
        return None

    if proc.returncode == 0:
        ppm_hint = _extract_ppm_from_output(proc.stdout)
        if ppm_hint is not None:
            print(f"[OK     ] rtl_test: ppm offset {ppm_hint} detected; consider updating config")
            return ppm_hint
        print("[OK     ] rtl_test: frequency drift measurement complete")
        return None

    snippet = (proc.stderr.strip() or proc.stdout.strip())[:120]
    print(f"[WARNING] rtl_test exit code {proc.returncode}: {snippet}")
    return None


def _report_connectivity(config: StationConfig) -> None:
    """Print connectivity status for KISS and APRS-IS endpoints."""

    result = probe_tcp_endpoint(config.kiss_host, config.kiss_port, timeout=1.0)
    if result.success:
        print(f"[OK     ] KISS: reachable at {config.kiss_host}:{config.kiss_port}")
    else:
        print(
            f"[WARNING] KISS: unable to reach {config.kiss_host}:{config.kiss_port} ({result.error})"
        )

    aprs_result = probe_tcp_endpoint(config.aprs_server, config.aprs_port, timeout=2.0)
    if aprs_result.success:
        print(f"[OK     ] APRS-IS: reachable at {config.aprs_server}:{config.aprs_port}")
    else:
        print(
            f"[WARNING] APRS-IS: unable to reach {config.aprs_server}:{config.aprs_port} ({aprs_result.error})"
        )


def _prompt_launch_direwolf_probe(config: StationConfig, config_dir: Path | None) -> None:
    """Offer to launch a short Direwolf capture when binaries are available."""

    if not _can_launch_direwolf():
        return
    if _prompt_yes_no("Launch Direwolf for a 15-second live capture?", default=False):
        _launch_direwolf_probe(config, config_dir)


def _print_ppm_tip(ppm_hint: str | None) -> None:
    """Output a configuration hint when a ppm offset measurement was captured."""

    if ppm_hint is not None:
        print(
            "Tip: set `ppm_correction` in the configuration to this value to improve tuning accuracy."
        )


def _extract_ppm_from_output(output: str) -> str | None:
    """Return the first rtl_test PPM line or None if not present."""

    for line in output.splitlines():
        line = line.strip()
        if "ppm" in line.lower() and any(ch.isdigit() for ch in line):
            return line
    return None


def _report_direwolf_log_summary() -> None:
    """Print a brief summary of recent Direwolf log entries if available."""

    log_dir = config_module.get_data_dir() / "logs"
    log_file = log_dir / "direwolf.log"
    if not log_file.exists():
        print(
            f"[WARNING] Direwolf log not found at {log_file}. Run `nesdr-igate listen` to generate logs."
        )
        return

    try:
        recent_lines = _tail_file(log_file, lines=6)
    except OSError as exc:
        print(f"[WARNING] Unable to read Direwolf log {log_file}: {exc}")
        return

    print(f"[OK     ] Direwolf log found at {log_file}")
    if recent_lines:
        print("    Recent log entries:")
        for line in recent_lines:
            print(f"      {line}")


def _tail_file(path: Path, *, lines: int) -> list[str]:
    """Return the last `lines` entries from a text file."""

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        buffer = deque(handle, maxlen=lines)
    return [entry.rstrip("\n") for entry in buffer]


def _can_launch_direwolf() -> bool:
    """Return True when rtl_fm and Direwolf binaries are both available."""

    return shutil.which("rtl_fm") is not None and shutil.which("direwolf") is not None


def _launch_direwolf_probe(config: StationConfig, config_dir: Path | None = None) -> None:
    """Run a short rtl_fm + Direwolf session capturing output to a temp log.

    Args:
        config: Station configuration providing frequency and gain defaults.
        config_dir: Preferred directory containing direwolf.conf; falls back to the
            global config directory when absent.
    """

    log_dir = config_module.get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    temp_log = log_dir / "direwolf_probe.log"

    rtl_cmd = [
        "rtl_fm",
        "-f",
        str(int(config.center_frequency_hz)),
        "-M",
        "fm",
        "-s",
        "22050",
        "-E",
        "deemp",
        "-A",
        "fast",
        "-F",
        "9",
    ]
    if config.gain is not None:
        rtl_cmd.extend(["-g", str(config.gain)])
    if config.ppm_correction is not None:
        rtl_cmd.extend(["-p", str(config.ppm_correction)])

    candidate_dirs: list[Path] = []
    if config_dir is not None:
        candidate_dirs.append(config_dir)
    default_dir = config_module.get_config_dir()
    if default_dir not in candidate_dirs:
        candidate_dirs.append(default_dir)

    direwolf_conf: Path | None = None
    for directory in candidate_dirs:
        candidate = directory / "direwolf.conf"
        if candidate.exists():
            direwolf_conf = candidate
            break

    if direwolf_conf is None:
        print("[WARNING] Cannot launch Direwolf probe: direwolf.conf not found")
        return

    direwolf_cmd = [
        "direwolf",
        "-c",
        str(direwolf_conf),
        "-r",
        "22050",
        "-t",
        "0",
        "-",
    ]

    rtl_proc: subprocess.Popen[bytes] | None = None
    try:
        rtl_proc = subprocess.Popen(
            rtl_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        print(f"[WARNING] Failed to start rtl_fm for probe: {exc}")
        return

    try:
        with open(temp_log, "w", encoding="utf-8") as log_handle:
            direwolf_proc = subprocess.Popen(
                direwolf_cmd,
                stdin=rtl_proc.stdout,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            try:
                direwolf_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                direwolf_proc.terminate()
                direwolf_proc.wait(timeout=5)
    except OSError as exc:
        print(f"[WARNING] Failed to start Direwolf for probe: {exc}")
    finally:
        if rtl_proc is not None:
            rtl_proc.terminate()
            try:
                rtl_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                rtl_proc.kill()

    try:
        probe_lines = _tail_file(temp_log, lines=5)
    except OSError as exc:
        print(f"[WARNING] Unable to read probe log {temp_log}: {exc}")
        return

    if probe_lines:
        print("[OK     ] Direwolf probe log:")
        for line in probe_lines:
            print(f"      {line}")
    else:
        print("[WARNING] Direwolf probe did not produce output; check connections.")

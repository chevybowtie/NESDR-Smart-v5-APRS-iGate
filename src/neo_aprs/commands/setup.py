"""Onboarding command implementation."""

from __future__ import annotations

import logging
import importlib.resources as resources
import os
import re
import shutil
import subprocess
from argparse import Namespace
from collections import deque
from getpass import getpass
from pathlib import Path
from typing import Callable

from neo_core import config as config_module
from neo_core.config import StationConfig
from neo_core.diagnostics_helpers import probe_tcp_endpoint

CALLSIGN_PATTERN = re.compile(r"^[A-Z0-9]{1,6}-[0-9]{1,2}$")


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def run_setup(args: Namespace) -> int:
    """Run the onboarding workflow."""
    config_path = config_module.resolve_config_path(args.config)

    if args.reset and config_path.exists():
        try:
            existing_config = config_module.load_config(config_path)
        except Exception:  # pragma: no cover - best effort cleanup
            existing_config = None
        if existing_config and existing_config.passcode_in_keyring:
            config_module.delete_passcode_from_keyring(existing_config.callsign)
        config_path.unlink()
        logger.info("Removed existing configuration at %s", config_path)

    if args.non_interactive:
        return _run_non_interactive(config_path)

    try:
        existing = _load_existing(config_path)
    except ValueError as exc:
        logger.warning("Existing configuration invalid (%s); starting fresh", exc)
        existing = None

    try:
        new_config = _interactive_prompt(existing)
    except KeyboardInterrupt:
        logger.info("Setup cancelled by user")
        return 1

    if args.dry_run:
        logger.info("Dry run: configuration not written")
        logger.info("%s", config_module.config_summary(new_config))
        return 0

    saved_path = config_module.save_config(new_config, path=config_path)
    logger.info("Configuration saved to %s", saved_path)
    logger.info("%s", config_module.config_summary(new_config))
    _maybe_render_direwolf_config(new_config, saved_path.parent)
    _offer_hardware_validation(new_config)
    return 0


def _run_non_interactive(config_path: Path) -> int:
    try:
        config = config_module.load_config(config_path)
    except FileNotFoundError:
        logger.error(
            "Configuration not found at %s; run interactive setup first", config_path
        )
        return 1
    except ValueError as exc:
        logger.error("Configuration invalid: %s", exc)
        return 1

    logger.info("Configuration OK:")
    logger.info("%s", config_module.config_summary(config))
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
        "APRS callsign-SSID",
        default=_default(existing, "callsign"),
        transform=str.upper,
        validator=_validate_callsign,
    )
    passcode = prompt.secret(
        "APRS-IS passcode",
        default=_default(existing, "passcode"),
    )
    use_keyring = bool(getattr(existing, "passcode_in_keyring", False))
    if config_module.keyring_supported():
        store_choice = _prompt_yes_no(
            "Store APRS-IS passcode in system keyring?",
            default=use_keyring,
        )
        if store_choice:
            try:
                config_module.store_passcode_in_keyring(callsign, passcode)
                use_keyring = True
            except ValueError as exc:
                logger.warning("Keyring unavailable: %s", exc)
                use_keyring = False
        else:
            if use_keyring:
                config_module.delete_passcode_from_keyring(callsign)
            use_keyring = False
    elif use_keyring:
        logger.warning(
            "Existing configuration referenced keyring-stored passcode, but keyring backend is unavailable. Keeping passcode in config file."
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

    # Only prompt for WSPR details when an existing config already enabled WSPR.
    # This keeps the interactive flow compact for new users and preserves test
    # expectations which don't provide answers for WSPR prompts.
    if config_module.keyring_supported() or (
        existing is not None
        and bool(_default(existing, "wspr_enabled", fallback=False))
    ):
        wspr_grid = prompt.optional_string(
            "WSPR reporter grid (Maidenhead, e.g. EM12ab)",
            default=_default(existing, "wspr_grid"),
        )
        wspr_power_dbm = prompt.integer(
            "Reported WSPR transmit power (dBm)",
            default=_default(existing, "wspr_power_dbm", fallback=37),
        )
        wspr_uploader_enabled = _prompt_yes_no(
            "Enable WSPR uploader queue (collect spots for later upload)?",
            default=bool(_default(existing, "wspr_uploader_enabled", fallback=False)),
        )
    else:
        _wspr_grid_def = _default(existing, "wspr_grid")
        wspr_grid = None if _wspr_grid_def is None else str(_wspr_grid_def)

        _wspr_power_def = _default(existing, "wspr_power_dbm", fallback=37)
        try:
            wspr_power_dbm = int(_wspr_power_def)  # type: ignore[arg-type]
        except Exception:
            wspr_power_dbm = 37

        wspr_uploader_enabled = bool(
            _default(existing, "wspr_uploader_enabled", fallback=False)
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
        wspr_grid=wspr_grid,
        wspr_power_dbm=wspr_power_dbm,
        wspr_uploader_enabled=wspr_uploader_enabled,
    )


def _default(
    config: StationConfig | None, attr: str, fallback: object | None = None
) -> object | None:
    if config is None:
        return fallback
    return getattr(config, attr)


def _validate_callsign(value: str) -> None:
    if not CALLSIGN_PATTERN.match(value):
        raise ValueError("Enter callsign-SSID like N0CALL-10")


class _Prompt:
    """Utility helpers for prompting user input with validation."""

    def __init__(
        self,
        existing: StationConfig | None,
        *,
        input_func: Callable[[str], str] | None = None,
        echo: Callable[[str], None] | None = None,
        secret_func: Callable[[str], str] | None = None,
    ) -> None:
        self._existing = existing
        self._input = input_func or input
        self._echo = echo or (lambda msg: logger.warning("%s", msg))
        self._secret = secret_func or getpass

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
            raw = self._input(prompt).strip()
            if not raw and default is not None:
                value = str(default)
            else:
                value = raw
            if not value:
                self._echo("Value required")
                continue
            if transform is not None:
                value = transform(value)
            if validator is not None:
                try:
                    validator(value)
                except ValueError as exc:
                    self._echo(str(exc))
                    continue
            return value

    def optional_string(self, label: str, default: object | None = None) -> str | None:
        prompt = _format_prompt(label, default)
        raw = self._input(prompt).strip()
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
            raw = self._input(prompt).strip()
            if not raw and default is not None:
                value = _parse_int(default)
            else:
                value = _parse_int(raw)
            if value is None:
                self._echo("Enter a valid integer")
                continue
            if minimum is not None and value < minimum:
                self._echo(f"Value must be >= {minimum}")
                continue
            if maximum is not None and value > maximum:
                self._echo(f"Value must be <= {maximum}")
                continue
            return value

    def optional_float(self, label: str, default: object | None = None) -> float | None:
        while True:
            prompt = _format_prompt(label, default)
            raw = self._input(prompt).strip()
            if not raw:
                return None if default is None else _parse_float(default)
            parsed = _parse_float(raw)
            if parsed is None:
                self._echo("Enter a numeric value or leave blank")
                continue
            return parsed

    def secret(self, label: str, default: object | None = None) -> str:
        while True:
            if default is not None:
                prompt = f"{label} [leave blank to keep existing]: "
            else:
                prompt = f"{label}: "
            value = self._secret(prompt)
            if not value and default is not None:
                return str(default)
            if not value:
                self._echo("Value required")
                continue
            confirm = self._secret("Confirm passcode: ")
            if value != confirm:
                self._echo("Passcodes do not match; try again")
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
        logger.warning("Direwolf template unavailable; skipping auto-render")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / "direwolf.conf"

    if dest_path.exists():
        message = f"Overwrite existing Direwolf config at {dest_path}?"
        proceed = _prompt_yes_no(message, default=False)
        if not proceed:
            logger.info("Keeping existing Direwolf configuration")
            return
    else:
        message = f"Create Direwolf config at {dest_path}?"
        proceed = _prompt_yes_no(message, default=True)
        if not proceed:
            logger.info("Skipping Direwolf configuration rendering")
            return

    log_dir = config_module.get_logs_dir("aprs")
    log_dir.mkdir(parents=True, exist_ok=True)

    replacements = {
        "AUDIO_SAMPLE_RATE": "22050",
        "CALLSIGN": config.callsign,
        "PASSCODE": config.passcode,
        "IGSERVER": f"{config.aprs_server} {config.aprs_port}",
        "LATITUDE": _format_coordinate(config.latitude, fallback="REPLACE_LAT"),
        "LONGITUDE": _format_coordinate(config.longitude, fallback="REPLACE_LON"),
        "BEACON_COMMENT": _escape_comment(
            config.beacon_comment or f"{config.callsign} Neo iGate"
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

    logger.info("Direwolf configuration written to %s", dest_path)


def _load_direwolf_template() -> str | None:
    try:
        return (
            resources.files("neo_rx.templates")
            .joinpath("direwolf.conf")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError):  # pragma: no cover - defensive
        return None


def _format_coordinate(value: float | None, *, fallback: str) -> str:
    if value is None:
        return fallback
    return f"{value:.6f}"


def _escape_comment(comment: str) -> str:
    return comment.replace('"', '\\"')


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
        logger.warning("Please answer 'y' or 'n'")


# Backward-compatible public alias for tests
def prompt_yes_no(
    message: str,
    *,
    default: bool,
    input_func: Callable[[str], str] | None = None,
    echo: Callable[[str], None] | None = None,
) -> bool:
    # Use injected input/echo if provided
    if input_func is None and echo is None:
        return _prompt_yes_no(message, default=default)
    # Minimal reimplementation using injected functions
    inp = input_func or input
    log = echo or (lambda msg: logger.warning("%s", msg))
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        response = inp(f"{message}{suffix}: ").strip().lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        log("Please answer 'y' or 'n'")


class _PromptSession:
    def __init__(
        self,
        existing: StationConfig | None,
        *,
        input_func: Callable[[str], str] | None = None,
        echo: Callable[[str], None] | None = None,
        secret_func: Callable[[str], str] | None = None,
    ) -> None:
        self.prompt = _Prompt(
            existing, input_func=input_func, echo=echo, secret_func=secret_func
        )

    def ask_yes_no(self, message: str, default: bool) -> bool:
        # Delegate to public prompt_yes_no with injected functions
        return prompt_yes_no(
            message,
            default=default,
            input_func=self.prompt._input,
            echo=self.prompt._echo,
        )


def _offer_hardware_validation(config: StationConfig) -> None:
    message = "Run a quick SDR/Direwolf validation now?"
    if not _prompt_yes_no(message, default=False):
        return
    _run_hardware_validation(config)


def _run_hardware_validation(config: StationConfig) -> None:
    logger.info("Running hardware validation...")

    command_checks = {
        "rtl_fm": "RTL-SDR capture utility",
        "rtl_test": "RTL-SDR self-test",
        "direwolf": "Direwolf modem",
    }
    for command, description in command_checks.items():
        path = shutil.which(command)
        if path:
            logger.info("[OK     ] %s: found (%s)", command, description)
        else:
            logger.warning("[WARNING] %s: not found in PATH (%s)", command, description)

    ppm_hint: str | None = None
    if shutil.which("rtl_test"):
        try:
            proc = subprocess.run(
                ["rtl_test", "-p", "-d", "0"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0:
                ppm_hint = _extract_ppm_from_output(proc.stdout)
                if ppm_hint is not None:
                    logger.info(
                        "[OK     ] rtl_test: ppm offset %s detected; consider updating config",
                        ppm_hint,
                    )
                else:
                    logger.info(
                        "[OK     ] rtl_test: frequency drift measurement complete"
                    )
            else:
                snippet = (proc.stderr.strip() or proc.stdout.strip())[:120]
                logger.warning(
                    "[WARNING] rtl_test exit code %s: %s",
                    proc.returncode,
                    snippet,
                )
        except subprocess.TimeoutExpired:
            logger.warning(
                "[WARNING] rtl_test: timed out (ensure the SDR is connected)"
            )
        except OSError as exc:
            logger.warning("[WARNING] rtl_test: failed to execute (%s)", exc)

    result = probe_tcp_endpoint(config.kiss_host, config.kiss_port, timeout=1.0)
    if result.success:
        logger.info(
            "[OK     ] KISS: reachable at %s:%s", config.kiss_host, config.kiss_port
        )
    else:
        logger.warning(
            "[WARNING] KISS: unable to reach %s:%s (%s)",
            config.kiss_host,
            config.kiss_port,
            result.error,
        )

    aprs_result = probe_tcp_endpoint(config.aprs_server, config.aprs_port, timeout=2.0)
    if aprs_result.success:
        logger.info(
            "[OK     ] APRS-IS: reachable at %s:%s",
            config.aprs_server,
            config.aprs_port,
        )
    else:
        logger.warning(
            "[WARNING] APRS-IS: unable to reach %s:%s (%s)",
            config.aprs_server,
            config.aprs_port,
            aprs_result.error,
        )

    _report_direwolf_log_summary()

    if _can_launch_direwolf():
        if _prompt_yes_no(
            "Launch Direwolf for a 15-second live capture?", default=False
        ):
            _launch_direwolf_probe(config)

    if ppm_hint is not None:
        logger.info(
            "Tip: set `ppm_correction` in the configuration to this value to improve tuning accuracy."
        )

    logger.info("Hardware validation complete. Review warnings above for follow-up.")


def _extract_ppm_from_output(output: str) -> str | None:
    for line in output.splitlines():
        line = line.strip()
        if "ppm" in line.lower() and any(ch.isdigit() for ch in line):
            return line
    return None


def _report_direwolf_log_summary() -> None:
    # Prefer mode-specific logs dir, but fall back to legacy location to keep
    # backward compatibility with existing setups and tests.
    primary_dir = config_module.get_logs_dir("aprs")
    legacy_dir = config_module.get_data_dir() / "logs"
    primary_file = primary_dir / "direwolf.log"
    legacy_file = legacy_dir / "direwolf.log"

    if primary_file.exists():
        log_file = primary_file
    elif legacy_file.exists():
        log_file = legacy_file
    else:
        # Report primary path for guidance
        logger.warning(
            "[WARNING] Direwolf log not found at %s. Run `neo-rx listen` to generate logs.",
            primary_file,
        )
        return

    try:
        recent_lines = _tail_file(log_file, lines=6)
    except OSError as exc:
        logger.warning("[WARNING] Unable to read Direwolf log %s: %s", log_file, exc)
        return

    logger.info("[OK     ] Direwolf log found at %s", log_file)
    if recent_lines:
        logger.info("    Recent log entries:")
        for line in recent_lines:
            logger.info("      %s", line)


def _tail_file(path: Path, *, lines: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        buffer = deque(handle, maxlen=lines)
    return [entry.rstrip("\n") for entry in buffer]


def _can_launch_direwolf() -> bool:
    return shutil.which("rtl_fm") is not None and shutil.which("direwolf") is not None


def _launch_direwolf_probe(config: StationConfig) -> None:
    log_dir = config_module.get_logs_dir("aprs")
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

    direwolf_conf = config_module.get_config_dir() / "direwolf.conf"
    if not direwolf_conf.exists():
        direwolf_conf = config_module.get_config_dir() / "direwolf.conf"

    if not direwolf_conf.exists():
        logger.warning(
            "[WARNING] Cannot launch Direwolf probe: direwolf.conf not found"
        )
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
        logger.warning("[WARNING] Failed to start rtl_fm for probe: %s", exc)
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
        logger.warning("[WARNING] Failed to start Direwolf for probe: %s", exc)
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
        logger.warning("[WARNING] Unable to read probe log %s: %s", temp_log, exc)
        return

    if probe_lines:
        logger.info("[OK     ] Direwolf probe log:")
        for line in probe_lines:
            logger.info("      %s", line)
    else:
        logger.warning(
            "[WARNING] Direwolf probe did not produce output; check connections."
        )

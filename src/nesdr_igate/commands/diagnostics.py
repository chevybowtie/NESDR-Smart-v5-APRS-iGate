"""Diagnostics command implementation."""

from __future__ import annotations

import json
import logging
import sys
import time
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, cast

from nesdr_igate import config as config_module
from nesdr_igate.config import StationConfig
from nesdr_igate.diagnostics_helpers import probe_tcp_endpoint
import shutil

try:  # Python 3.10+ exposes metadata here
    from importlib import metadata as importlib_metadata
    # from nesdr_igate import __version__
except ImportError:  # pragma: no cover - fallback for older runtimes
    import importlib_metadata  # type: ignore[no-redef]

SectionStatus = str


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _package_version() -> str:
    # Attempt to read the package-level canonical version. Importing the
    # package at function time avoids import-order problems during static
    # analysis while still returning the centralized value at runtime.
    try:
        from nesdr_igate import __version__ as ver

        return ver
    except Exception:
        try:
            return importlib_metadata.version("nesdr-igate")
        except importlib_metadata.PackageNotFoundError:
            return "0.0.0"


@dataclass(slots=True)
class Section:
    """Represents the status of a diagnostic check."""

    name: str
    status: SectionStatus
    message: str
    details: dict[str, Any]


def run_diagnostics(args: Namespace) -> int:
    """Run system diagnostics and emit results in the requested format."""
    config_path = config_module.resolve_config_path(getattr(args, "config", None))

    sections: list[Section] = []

    sections.append(_check_environment())
    config_section, station_config = _check_config(config_path)
    sections.append(config_section)
    sections.append(_check_sdr())
    sections.append(_check_direwolf(station_config))
    sections.append(_check_aprs_is(station_config))

    generated_at = time.time()
    summary = _summarize_sections(sections)

    if getattr(args, "json", False):
        report = _sections_to_mapping(sections)
        report["meta"] = {
            "tool": "nesdr-igate",
            "version": _package_version(),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(generated_at)),
        }
        report["summary"] = summary
        indent = 2 if getattr(args, "verbose", False) else None
        print(json.dumps(report, indent=indent, default=_json_default))
    else:
        _print_text_report(sections, verbose=getattr(args, "verbose", False))

    if not getattr(args, "json", False):
        _log_summary(summary)

    return 1 if any(section.status == "error" for section in sections) else 0


def _check_environment() -> Section:
    venv_active = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    status: SectionStatus = "ok" if venv_active else "warning"
    message = "Virtualenv active" if venv_active else "Using system interpreter"

    packages = {}
    missing: list[str] = []
    for package in ("numpy", "pyrtlsdr", "aprslib"):
        try:
            packages[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            packages[package] = None
            missing.append(package)

    if missing:
        status = "warning"
        message += f"; Missing packages: {', '.join(missing)}"
    else:
        message += "; Required packages present"

    details = {
        "python_version": sys.version.split()[0],
        "venv_active": venv_active,
        "sys_prefix": sys.prefix,
        "packages": packages,
    }

    return Section("Environment", status, message, details)


def _check_config(config_path: Path) -> tuple[Section, StationConfig | None]:
    if not config_path.exists():
        message = f"No config file found at {config_path}"
        section = Section(
            "Config",
            "warning",
            message,
            {"path": str(config_path)},
        )
        return section, None

    try:
        config = config_module.load_config(config_path)
    except Exception as exc:  # pragma: no cover - depends on malformed file
        return (
            Section(
                "Config",
                "error",
                f"Failed to load configuration: {exc}",
                {"path": str(config_path)},
            ),
            None,
        )

    details = {
        "path": str(config_path),
        "callsign": config.callsign,
        "aprs_server": f"{config.aprs_server}:{config.aprs_port}",
        "kiss": f"{config.kiss_host}:{config.kiss_port}",
        "summary": config_module.config_summary(config),
    }
    section = Section("Config", "ok", f"Loaded config for {config.callsign}", details)
    return section, config


def _check_sdr() -> Section:
    try:
        from rtlsdr import RtlSdr  # type: ignore[import]
    except ImportError as exc:
        return Section(
            "SDR",
            "warning",
            "pyrtlsdr not installed; SDR checks skipped",
            {"error": str(exc)},
        )

    rtl_sdr_cls = cast(Any, RtlSdr)
    # The pyrtlsdr package historically exposed class helpers like
    # RtlSdr.get_device_count() and RtlSdr.get_device_serial_addresses().
    # Some versions (or alternative builds) may not expose these helpers
    # and instead require instantiation to probe device presence. Try the
    # class helpers first, and fall back to attempting to open device 0.
    details: dict[str, Any] = {}

    # Primary path: class-level helpers
    if hasattr(rtl_sdr_cls, "get_device_count") and callable(
        getattr(rtl_sdr_cls, "get_device_count")
    ):
        try:
            device_count = rtl_sdr_cls.get_device_count()
            details["device_count"] = device_count
            try:
                serials = rtl_sdr_cls.get_device_serial_addresses()
            except Exception:  # pragma: no cover - best effort only
                serials = []
            if serials:
                details["serials"] = [
                    s.decode() if isinstance(s, bytes) else str(s) for s in serials
                ]
        except Exception as exc:  # pragma: no cover - hardware specific failures
            return Section(
                "SDR",
                "error",
                f"Failed to query RTL-SDR devices: {exc}",
                {"error": str(exc)},
            )

        if device_count == 0:
            return Section("SDR", "warning", "No RTL-SDR devices detected", details)

        return Section("SDR", "ok", f"Detected {device_count} RTL-SDR device(s)", details)

    # Fallback: try instantiating a device handle (best-effort).
    # If instantiation succeeds, assume at least one device is present.
    try:
        # Some RtlSdr implementations accept device_index as a kwarg,
        # others accept it positionally. Try both styles.
        try:
            sdr_inst = rtl_sdr_cls(device_index=0)  # type: ignore[call-arg]
        except TypeError:
            sdr_inst = rtl_sdr_cls(0)  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover - best effort to probe
        # If we can't instantiate, treat it as a warning rather than a
        # hard error — the environment may still be fine for rtl_fm usage.
        return Section(
            "SDR",
            "warning",
            "Unable to probe RTL-SDR devices via pyrtlsdr; device open failed",
            {"error": str(exc)},
        )

    # We managed to open a device handle — collect some basic metadata and
    # then close it. Prefer attributes on the instance for serial information.
    try:
        serial = getattr(sdr_inst, "serial_number", None)
    except Exception:
        serial = None

    try:
        # Close handle if it has a close method
        close_fn = getattr(sdr_inst, "close", None)
        if callable(close_fn):
            close_fn()
    except Exception:
        # ignore close failures for diagnostics
        pass

    details["device_count"] = 1
    if serial is not None:
        details["serials"] = [serial.decode() if isinstance(serial, bytes) else str(serial)]

    return Section("SDR", "ok", "Detected at least 1 RTL-SDR device", details)


def _check_direwolf(config: StationConfig | None) -> Section:
    if config is None:
        return Section(
            "Direwolf",
            "warning",
            "Configuration unavailable; skipping KISS connectivity check",
            {},
        )

    host, port = config.kiss_host, config.kiss_port
    # If the direwolf binary isn't present, avoid attempting network checks
    # and give a clearer message that Direwolf must be installed/started by
    # the `listen` command.
    if shutil.which("direwolf") is None:
        return Section(
            "Direwolf",
            "warning",
            "Direwolf not installed; KISS connectivity checks skipped",
            {"installed": False},
        )

    result = probe_tcp_endpoint(host, port, timeout=1.0)
    if result.success:
        return Section(
            "Direwolf",
            "ok",
            f"KISS endpoint reachable at {host}:{port}",
            {"latency_ms": result.latency_ms, "installed": True},
        )

    # Connection refused is expected when Direwolf is installed but not
    # currently running (e.g., before `nesdr-igate listen` starts it).
    err = (result.error or "").lower()
    if ("connection" in err and "refused" in err) or ("errno 111" in err):
        message = (
            f"Direwolf installed but not running locally; KISS endpoint unreachable at {host}:{port}"
        )
    else:
        message = f"Unable to reach Direwolf KISS at {host}:{port}"

    return Section(
        "Direwolf",
        "warning",
        message,
        {"error": result.error, "installed": True},
    )


def _check_aprs_is(config: StationConfig | None) -> Section:
    if config is None:
        return Section(
            "APRS-IS",
            "warning",
            "Configuration unavailable; skipping APRS-IS connectivity check",
            {},
        )

    host, port = config.aprs_server, config.aprs_port
    result = probe_tcp_endpoint(host, port, timeout=2.0)
    if result.success:
        return Section(
            "APRS-IS",
            "ok",
            f"Reachable APRS-IS server {host}:{port}",
            {"latency_ms": result.latency_ms},
        )
    return Section(
        "APRS-IS",
        "warning",
        f"Unable to reach APRS-IS server {host}:{port}",
        {"error": result.error},
    )


def _sections_to_mapping(sections: Iterable[Section]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for section in sections:
        key = section.name.lower().replace(" ", "_")
        report[key] = {
            "status": section.status,
            "message": section.message,
            "details": section.details,
        }
    return report


def _summarize_sections(sections: Iterable[Section]) -> dict[str, Any]:
    errors = [section.name for section in sections if section.status == "error"]
    warnings = [section.name for section in sections if section.status == "warning"]
    return {
        "errors": len(errors),
        "warnings": len(warnings),
        "error_sections": errors,
        "warning_sections": warnings,
    }


def _log_summary(summary: dict[str, Any]) -> None:
    level = logging.INFO
    if summary.get("errors", 0):
        level = logging.ERROR
    elif summary.get("warnings", 0):
        level = logging.WARNING

    error_sections = ", ".join(summary.get("error_sections", [])) or "-"
    warning_sections = ", ".join(summary.get("warning_sections", [])) or "-"

    logger.log(
        level,
        "Diagnostics summary: errors=%s warnings=%s error_sections=%s warning_sections=%s",
        summary.get("errors", 0),
        summary.get("warnings", 0),
        error_sections,
        warning_sections,
    )


def _print_text_report(sections: Iterable[Section], *, verbose: bool) -> None:
    for section in sections:
        logger.info(
            "[%s] %s: %s",
            section.status.upper().ljust(7),
            section.name,
            section.message,
        )
        if verbose and section.details:
            for key, value in section.details.items():
                formatted_value = _format_detail_value(value)
                logger.info("    %s: %s", key, formatted_value)


def _format_detail_value(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items()) or "{}"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(map(str, value))
    return str(value)


def _json_default(value: Any) -> Any:  # pragma: no cover - exercised only when needed
    if isinstance(value, Path):
        return str(value)
    return str(value)

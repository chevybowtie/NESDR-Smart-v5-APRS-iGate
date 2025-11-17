"""Calibration helpers for WSPR.

Helpers to estimate frequency offset from observed decoded spots and
convert that offset into parts-per-million (ppm) which can be applied
to the radio driver. Includes a small JSON-lines loader useful for
post-processing captured spot files.
"""

from __future__ import annotations

import logging
from typing import Optional, Iterable
from statistics import median
from pathlib import Path
import json

LOG = logging.getLogger(__name__)


def compute_ppm_from_offset(freq_hz: float, offset_hz: float) -> float:
    """Compute parts-per-million correction given an offset in Hz."""
    if freq_hz == 0:
        raise ValueError("freq_hz must be non-zero")
    ppm = (offset_hz / freq_hz) * 1_000_000.0
    LOG.debug("Computed ppm=%s from freq=%s offset=%s", ppm, freq_hz, offset_hz)
    return ppm


def apply_ppm_to_radio(ppm: float) -> None:
    """Apply ppm correction to the radio driver (requires implementation)."""
    from neo_rx._compat import prepare_rtlsdr

    # Prepare RTL-SDR with compatibility patches
    prepare_rtlsdr()

    try:
        from rtlsdr import RtlSdr
    except ImportError as exc:
        LOG.error("RTL-SDR library not available: %s", exc)
        raise RuntimeError("RTL-SDR driver unavailable") from exc

    try:
        # Check for available devices
        device_count = RtlSdr.get_device_count()  # type: ignore[attr-defined]
        if device_count == 0:
            raise RuntimeError("No RTL-SDR devices found")

        sdr = RtlSdr()  # type: ignore[operator]
        try:
            # Apply PPM correction
            sdr.set_ppm_offset(int(round(ppm)))  # type: ignore[attr-defined]
            LOG.info("Applied ppm correction %s to RTL-SDR device", ppm)
        finally:
            sdr.close()
    except Exception as exc:
        LOG.error("Failed to apply ppm correction to RTL-SDR: %s", exc)
        raise RuntimeError(f"RTL-SDR ppm application failed: {exc}") from exc


def persist_ppm_to_config(ppm: float, config_path: str | None = None) -> None:
    """Persist computed ppm into the station configuration file.

    Writes the rounded integer `ppm_correction` into the `StationConfig`
    and saves it to `config_path` if provided or the default config
    location otherwise.
    """
    try:
        from neo_rx import config as config_module
    except Exception:
        LOG.error("Configuration module unavailable; cannot write ppm to config")
        raise RuntimeError("Configuration module not available")

    try:
        cfg = config_module.load_config(config_path) if config_path else config_module.load_config()
        cfg.ppm_correction = int(round(float(ppm)))

        # Resolve the real target config path we will write to
        try:
            target_path = config_module.resolve_config_path() if config_path is None else Path(config_path)
        except Exception:
            target_path = Path(config_path) if config_path else None

        # Create an automatic timestamped backup of existing config, if present
        try:
            import shutil
            from neo_rx.timeutils import utc_timestamp

            if target_path is not None and target_path.exists():
                # use a dedicated backups directory under the config dir
                try:
                    cfg_dir = target_path.parent
                    backups_dir = cfg_dir / "backups"
                    backups_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    backups_dir = target_path.parent

                ts = utc_timestamp()
                backup = backups_dir / (target_path.name + f".bak-{ts}")
                try:
                    shutil.copy(target_path, backup)
                    LOG.info("Created config backup: %s", backup)
                except Exception:
                    LOG.exception("Failed to create config backup for %s", target_path)
        except Exception:
            LOG.exception("Unexpected error while attempting to create config backup")

        config_module.save_config(cfg, config_path)
        try:
            cfg_path_repr = str(target_path) if target_path is not None else str(config_path)
        except Exception:
            cfg_path_repr = str(config_path)
        LOG.info("Saved ppm_correction=%s to config %s", cfg.ppm_correction, cfg_path_repr)
    except Exception:
        LOG.exception("Failed to persist ppm to config")
        raise


def estimate_offset_from_spots(spots: Iterable[dict], expected_freq_hz: Optional[float] = None) -> dict:
    """Estimate frequency offset (Hz) and derived ppm from an iterable of spot dicts.

    Each spot dict is expected to contain a numeric `freq_hz` key and optionally
    an `snr_db` key. If `expected_freq_hz` is omitted the function will compute
    the median observed frequency and return an offset of 0 (caller may prefer
    to provide an expected frequency explicitly).
    """
    freqs: list[float] = []
    snrs: list[float] = []
    for s in spots:
        try:
            freq_val = s.get("freq_hz")
            if freq_val is not None:
                f = float(freq_val)
                freqs.append(f)
        except (TypeError, ValueError):
            continue
        try:
            snr_val = s.get("snr_db")
            if snr_val is not None:
                snrs.append(float(snr_val))
        except (TypeError, ValueError):
            pass

    if not freqs:
        raise ValueError("No frequency observations in spots")

    median_freq = median(freqs)
    count = len(freqs)
    median_snr = median(snrs) if snrs else None

    if expected_freq_hz is None:
        offset_hz = 0.0
        ppm = 0.0
    else:
        offset_hz = median_freq - float(expected_freq_hz)
        ppm = compute_ppm_from_offset(expected_freq_hz, offset_hz)

    return {
        "median_observed_freq_hz": median_freq,
        "offset_hz": offset_hz,
        "ppm": ppm,
        "median_snr_db": median_snr,
        "count": count,
    }


def load_spots_from_jsonl(path: Path) -> list[dict]:
    """Load JSON-lines file containing spot dicts and return as a list."""
    spots: list[dict] = []
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    spots.append(json.loads(line))
                except Exception:
                    LOG.exception("Skipping malformed JSON line in %s", path)
    except FileNotFoundError:
        LOG.debug("Spots file not found: %s", path)
    return spots

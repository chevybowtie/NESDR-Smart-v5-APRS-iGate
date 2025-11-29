"""WSPRNet uploader with durable on-disk queue and HTTP client."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, cast

# Import version from neo_rx package to maintain compatibility during migration
try:
    from neo_rx import __version__
except ImportError:
    __version__ = "0.2.2"  # Fallback during development

LOG = logging.getLogger(__name__)

try:  # Optional dependency enabled via the ``wspr`` extra
    import requests
except ImportError:  # pragma: no cover - surfaced at runtime if extra missing
    requests = None  # type: ignore[assignment]


DEFAULT_ENDPOINT = "https://wsprnet.org/post"
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 10
DAEMON_BACKOFF_BASE_S = 30.0
DAEMON_BACKOFF_MAX_S = 600.0
DAEMON_BACKOFF_MULTIPLIER = 2.0


class WsprUploader:
    """Durable queue plus HTTP uploader for wsprnet.org."""

    def __init__(
        self,
        credentials: Dict[str, str] | None = None,
        queue_path: str | Path | None = None,
        base_url: str | None = None,
        session: object | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if requests is None:  # pragma: no cover - exercised when extra missing
            raise RuntimeError(
                "The 'requests' package is required for WSPR uploads. Install neo-rx with the 'wspr' extra (pip install -e '.[wspr]')."
            )

        self.credentials = credentials or {}
        self.queue_path = (
            Path(queue_path)
            if queue_path is not None
            else Path("./data/wspr_upload_queue.jsonl")
        )
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

        self.base_url = base_url or DEFAULT_ENDPOINT
        self._timeout = (CONNECT_TIMEOUT_S, READ_TIMEOUT_S)
        self._version_tag = _build_version_tag(__version__)
        self._user_agent = f"neo-rx/{__version__}"
        self._session: Any = session or requests.Session()
        self._session.headers.setdefault("User-Agent", self._user_agent)
        self._clock = clock or time.monotonic
        self._daemon_backoff_current = DAEMON_BACKOFF_BASE_S
        self._daemon_backoff_next = 0.0
        self._last_upload_error: Optional[str] = None

    # --- Queue management -------------------------------------------------
    def enqueue_spot(self, spot: Dict) -> None:
        """Append a spot to the on-disk queue (JSON-lines)."""
        try:
            with self.queue_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(spot, default=str) + "\n")
        except Exception:
            LOG.exception("Failed to enqueue spot to %s", self.queue_path)

    def _read_queue(self) -> List[Dict]:
        if not self.queue_path.exists():
            return []
        items: List[Dict] = []
        try:
            with self.queue_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        LOG.exception("Skipping malformed queue line")
        except FileNotFoundError:
            return []
        return items

    def _rewrite_queue(self, remaining: Iterable[Dict]) -> None:
        # Atomic-ish rewrite via temp file then replace
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix="wspr_queue_", dir=str(self.queue_path.parent)
        )
        os.close(tmp_fd)
        tmp_file = Path(tmp_path)
        try:
            with tmp_file.open("w", encoding="utf-8") as fh:
                for item in remaining:
                    fh.write(json.dumps(item, default=str) + "\n")
            tmp_file.replace(self.queue_path)
        finally:
            try:
                if tmp_file.exists():
                    tmp_file.unlink(missing_ok=True)
            except Exception:
                pass

    # --- Uploading --------------------------------------------------------
    def upload_spot(self, spot: Dict) -> bool:
        """Upload a single spot to WSPRNet via HTTPS GET."""

        self._last_upload_error = None
        params = self._build_query_params(spot)
        if params is None:
            if self._last_upload_error is None:
                self._last_upload_error = "Spot missing metadata required for upload"
            return False
        success_message = f"Uploaded WSPR spot {params.get('tcall')} ({params.get('tgrid')} → {params.get('rgrid')})"
        return self._perform_request(params, success_log=success_message)

    def send_heartbeat(
        self,
        *,
        reporter_call: str,
        reporter_grid: str,
        dial_freq_hz: float,
        target_freq_hz: float | None = None,
        reporter_power_dbm: float | int | None = None,
        percent_time: float | int | None = None,
    ) -> bool:
        """Send a wsprstat heartbeat when no uploads were performed."""

        self._last_upload_error = None
        params = self._build_stat_params(
            reporter_call=reporter_call,
            reporter_grid=reporter_grid,
            dial_freq_hz=dial_freq_hz,
            target_freq_hz=target_freq_hz,
            reporter_power_dbm=reporter_power_dbm,
            percent_time=percent_time,
        )
        if params is None:
            if self._last_upload_error is None:
                self._last_upload_error = "Heartbeat missing metadata"
            return False

        success_message = (
            f"Sent WSPR heartbeat for {params.get('rcall')} at {params.get('rqrg')} MHz"
        )
        return self._perform_request(params, success_log=success_message)

    def drain(
        self, max_items: Optional[int] = None, *, daemon: bool = False
    ) -> Dict[str, Any]:
        """Attempt to upload queued spots; keep failures and unattempted in the queue.

        Returns a dict with counts: {"attempted", "succeeded", "failed"}.
        Failed items (failed uploads) are kept in the queue.
        Unattempted items (beyond max_items) are also kept in the queue.
        """
        items = self._read_queue()
        if not items:
            if daemon:
                self._reset_daemon_backoff()
            return {"attempted": 0, "succeeded": 0, "failed": 0}

        if daemon and not self._daemon_ready():
            remaining = max(0.0, self._daemon_backoff_next - self._clock())
            return {
                "attempted": 0,
                "succeeded": 0,
                "failed": len(items),
                "skipped_due_to_backoff": True,
                "next_attempt_in": remaining,
            }

        attempted = 0
        succeeded = 0
        failed_items: List[Dict] = []
        first_error: Optional[str] = None

        for idx, spot in enumerate(items):
            if max_items is not None and attempted >= max_items:
                # Keep unattempted items in the queue
                failed_items.extend(items[idx:])
                break
            attempted += 1
            try:
                ok = self.upload_spot(spot)
            except Exception as exc:
                LOG.exception("Uploader threw; keeping spot in queue")
                ok = False
                if first_error is None:
                    first_error = f"Exception while uploading {spot.get('call')}: {exc}"
                if self._last_upload_error is None:
                    self._last_upload_error = first_error
            if ok:
                succeeded += 1
            else:
                failed_items.append(spot)
                if first_error is None:
                    reason = (
                        self._last_upload_error
                        or f"Upload failed for {spot.get('call')}"
                    )
                    first_error = reason

        self._rewrite_queue(failed_items)
        result: Dict[str, Any] = {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": len(failed_items),
        }
        if first_error:
            result["last_error"] = first_error

        if daemon and attempted > 0:
            if succeeded == 0:
                delay = self._record_daemon_failure()
                result["backoff_seconds"] = delay
            else:
                self._reset_daemon_backoff()

        return result

    @property
    def last_error(self) -> Optional[str]:
        return self._last_upload_error

    # --- Helpers ----------------------------------------------------------
    def _build_query_params(self, spot: Dict) -> Dict | None:
        self._last_upload_error = None
        missing: list[str] = []

        reporter_call = _as_str(spot.get("reporter_callsign"))
        reporter_grid = _as_str(spot.get("reporter_grid"))
        reporter_power_raw = spot.get("reporter_power_dbm")
        reporter_power: Optional[float] = None
        if reporter_power_raw is not None:
            try:
                reporter_power = float(reporter_power_raw)
            except (TypeError, ValueError):
                reporter_power = None

        target_call = _as_str(spot.get("call"))
        target_grid = _as_str(spot.get("grid"))

        freq_raw = spot.get("freq_hz")
        freq_hz: Optional[float] = None
        if freq_raw is not None:
            try:
                freq_hz = float(freq_raw)
            except (TypeError, ValueError):
                freq_hz = None

        dial_freq_raw = spot.get("dial_freq_hz")
        dial_freq_hz: Optional[float] = None
        if dial_freq_raw is not None:
            try:
                dial_freq_hz = float(dial_freq_raw)
            except (TypeError, ValueError):
                dial_freq_hz = None

        snr_raw = spot.get("snr_db")
        snr_db: Optional[float] = None
        if snr_raw is not None:
            try:
                snr_db = float(snr_raw)
            except (TypeError, ValueError):
                snr_db = None

        slot_start = _parse_slot_start(spot.get("slot_start_utc"))

        if not reporter_call:
            missing.append("reporter_callsign")
        if not reporter_grid:
            missing.append("reporter_grid")
        if reporter_power is None:
            missing.append("reporter_power_dbm")
        if not target_call:
            missing.append("call")
        if not target_grid:
            missing.append("grid")
        if freq_hz is None:
            missing.append("freq_hz")
        if dial_freq_hz is None:
            missing.append("dial_freq_hz")
        if snr_db is None:
            missing.append("snr_db")
        if slot_start is None:
            missing.append("slot_start_utc")

        if missing:
            missing_fields = ", ".join(sorted(missing))
            LOG.warning(
                "Skipping WSPR upload; spot missing metadata: %s",
                missing_fields,
            )
            self._last_upload_error = f"Spot missing metadata: {missing_fields}"
            return None

        reporter_call = cast(str, reporter_call)
        reporter_grid = cast(str, reporter_grid)
        target_call = cast(str, target_call)
        target_grid = cast(str, target_grid)
        slot_start = cast(datetime, slot_start)
        dial_freq_hz = cast(float, dial_freq_hz)
        freq_hz = cast(float, freq_hz)
        snr_db = cast(float, snr_db)
        reporter_power = cast(float, reporter_power)

        params = {
            "function": "wspr",
            "rcall": reporter_call,
            "rgrid": reporter_grid,
            "rqrg": _format_freq_mhz(dial_freq_hz),
            "date": slot_start.strftime("%y%m%d"),
            "time": slot_start.strftime("%H%M"),
            "sig": f"{int(round(snr_db))}",
            "dt": f"{float(spot.get('dt', 0.0)):.1f}",
            "drift": f"{int(round(float(spot.get('drift', 0.0) or 0.0)))}",
            "tqrg": _format_freq_mhz(freq_hz),
            "tcall": target_call,
            "tgrid": target_grid,
            "dbm": f"{int(round(reporter_power))}",
            "version": self._version_tag,
            "mode": "2",
        }
        return params

    def _build_stat_params(
        self,
        *,
        reporter_call: object,
        reporter_grid: object,
        dial_freq_hz: object,
        target_freq_hz: object | None,
        reporter_power_dbm: object | None,
        percent_time: object | None,
    ) -> Dict | None:
        missing: list[str] = []

        call = _as_str(reporter_call)
        if not call:
            missing.append("reporter_callsign")

        grid = _as_str(reporter_grid)
        if not grid:
            missing.append("reporter_grid")

        dial_freq = _as_float(dial_freq_hz)
        if dial_freq is None:
            missing.append("dial_freq_hz")

        target_freq = _as_float(
            target_freq_hz if target_freq_hz is not None else dial_freq
        )
        if target_freq is None:
            missing.append("target_freq_hz")

        power = _as_float(reporter_power_dbm)
        if power is None:
            missing.append("reporter_power_dbm")

        pct = _as_float(percent_time if percent_time is not None else 100.0)
        if pct is None:
            missing.append("percent_time")

        if missing:
            missing_fields = ", ".join(sorted(missing))
            LOG.warning("Skipping WSPR heartbeat; missing metadata: %s", missing_fields)
            self._last_upload_error = f"Heartbeat missing metadata: {missing_fields}"
            return None

        pct = cast(float, pct)
        dial_freq = cast(float, dial_freq)
        target_freq = cast(float, target_freq)
        power = cast(float, power)
        pct = max(0.0, min(100.0, pct))

        params = {
            "function": "wsprstat",
            "rcall": call,
            "rgrid": grid,
            "rqrg": _format_freq_mhz(dial_freq),
            "tpct": f"{int(round(pct))}",
            "tqrg": _format_freq_mhz(target_freq),
            "dbm": f"{int(round(power))}",
            "version": self._version_tag,
            "mode": "2",
        }
        return params

    def _perform_request(self, params: Dict[str, str], *, success_log: str) -> bool:
        function = params.get("function", "wspr")
        LOG.debug(
            "WSPR %s attempt for rcall=%s target=%s",
            function,
            params.get("rcall"),
            params.get("tcall") or params.get("tqrg"),
        )
        try:
            response = self._session.get(
                self.base_url, params=params, timeout=self._timeout
            )
        except (
            Exception
        ) as exc:  # requests.RequestException but keep generic for typing
            LOG.warning("WSPR %s request failed: %s", function, exc)
            self._last_upload_error = f"Request error: {exc}"
            return False

        if response.status_code != 200:
            LOG.warning("WSPR %s HTTP %s", function, response.status_code)
            self._last_upload_error = f"HTTP {response.status_code} during {function}"
            return False

        body = (response.text or "").strip()
        if not body:
            LOG.warning("WSPR %s returned empty response", function)
            self._last_upload_error = "Empty response body from WSPRnet"
            return False

        LOG.info("%s via %s", success_log, self.base_url)
        LOG.debug("WSPR %s response: %s", function, body[:200])
        self._last_upload_error = None
        return True

    def _daemon_ready(self) -> bool:
        return self._clock() >= self._daemon_backoff_next

    def _record_daemon_failure(self) -> float:
        delay = self._daemon_backoff_current
        self._daemon_backoff_next = self._clock() + delay
        self._daemon_backoff_current = min(
            self._daemon_backoff_current * DAEMON_BACKOFF_MULTIPLIER,
            DAEMON_BACKOFF_MAX_S,
        )
        return delay

    def _reset_daemon_backoff(self) -> None:
        self._daemon_backoff_current = DAEMON_BACKOFF_BASE_S
        self._daemon_backoff_next = 0.0


def _format_freq_mhz(freq_hz: float) -> str:
    return f"{freq_hz / 1_000_000:.6f}"


def _parse_slot_start(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_version_tag(version: str) -> str:
    candidate = f"neo-rx-{version}"
    if len(candidate) <= 10:
        return candidate
    compact = version.replace(".", "")
    candidate = f"neo-rx-{compact}"
    if len(candidate) <= 10:
        return candidate
    return candidate[:10]


def _as_str(value: object | None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any | None) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

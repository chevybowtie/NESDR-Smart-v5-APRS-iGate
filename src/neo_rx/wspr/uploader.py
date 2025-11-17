"""WSPRNet uploader with durable on-disk queue and HTTP client."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, cast

from neo_rx import __version__

LOG = logging.getLogger(__name__)

try:  # Optional dependency enabled via the ``wspr`` extra
    import requests
except ImportError:  # pragma: no cover - surfaced at runtime if extra missing
    requests = None  # type: ignore[assignment]


DEFAULT_ENDPOINT = "https://wsprnet.org/post"
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 10


class WsprUploader:
    """Durable queue plus HTTP uploader for wsprnet.org."""

    def __init__(
        self,
        credentials: Dict[str, str] | None = None,
        queue_path: str | Path | None = None,
        base_url: str | None = None,
        session: object | None = None,
    ) -> None:
        if requests is None:  # pragma: no cover - exercised when extra missing
            raise RuntimeError(
                "The 'requests' package is required for WSPR uploads. Install neo-rx with the 'wspr' extra (pip install -e '.[wspr]')."
            )

        self.credentials = credentials or {}
        self.queue_path = Path(queue_path) if queue_path is not None else Path("./data/wspr_upload_queue.jsonl")
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

        self.base_url = base_url or DEFAULT_ENDPOINT
        self._timeout = (CONNECT_TIMEOUT_S, READ_TIMEOUT_S)
        self._version_tag = _build_version_tag(__version__)
        self._user_agent = f"neo-rx/{__version__}"
        self._session: Any = session or requests.Session()
        self._session.headers.setdefault("User-Agent", self._user_agent)

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
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="wspr_queue_", dir=str(self.queue_path.parent))
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

        params = self._build_query_params(spot)
        if params is None:
            return False

        try:
            response = self._session.get(self.base_url, params=params, timeout=self._timeout)
        except Exception as exc:  # requests.RequestException but keep generic for typing
            LOG.warning("WSPR upload failed for %s: %s", params.get("tcall"), exc)
            return False

        if response.status_code != 200:
            LOG.warning(
                "WSPR upload HTTP %s for %s (rcall=%s)",
                response.status_code,
                params.get("tcall"),
                params.get("rcall"),
            )
            return False

        body = (response.text or "").strip()
        if not body:
            LOG.warning("WSPR upload returned empty response for %s", params.get("tcall"))
            return False

        LOG.info(
            "Uploaded WSPR spot %s (%s → %s) via %s",
            params.get("tcall"),
            params.get("tgrid"),
            params.get("rgrid"),
            self.base_url,
        )
        LOG.debug("WSPR upload response: %s", body[:200])
        return True

    def drain(self, max_items: Optional[int] = None) -> Dict[str, int]:
        """Attempt to upload queued spots; keep failures and unattempted in the queue.

        Returns a dict with counts: {"attempted", "succeeded", "failed"}.
        Failed items (failed uploads) are kept in the queue.
        Unattempted items (beyond max_items) are also kept in the queue.
        """
        items = self._read_queue()
        if not items:
            return {"attempted": 0, "succeeded": 0, "failed": 0}

        attempted = 0
        succeeded = 0
        failed_items: List[Dict] = []

        for idx, spot in enumerate(items):
            if max_items is not None and attempted >= max_items:
                # Keep unattempted items in the queue
                failed_items.extend(items[idx:])
                break
            attempted += 1
            try:
                ok = self.upload_spot(spot)
            except Exception:
                LOG.exception("Uploader threw; keeping spot in queue")
                ok = False
            if ok:
                succeeded += 1
            else:
                failed_items.append(spot)

        self._rewrite_queue(failed_items)
        return {"attempted": attempted, "succeeded": succeeded, "failed": len(failed_items)}

    # --- Helpers ----------------------------------------------------------
    def _build_query_params(self, spot: Dict) -> Dict | None:
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
            LOG.warning(
                "Skipping WSPR upload; spot missing metadata: %s",
                ", ".join(sorted(missing)),
            )
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

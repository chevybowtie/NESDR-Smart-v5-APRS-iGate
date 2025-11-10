"""WSPRNet uploader with simple on-disk queue.

Handles optional, opt-in upload of decoded spots to wsprnet.org. Provides a
lightweight on-disk queue so spots can be safely persisted when offline and
retried later. Network upload is kept abstract via ``upload_spot`` to avoid a
hard dependency on any specific HTTP client during early development.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional
from pathlib import Path
import json
import tempfile
import os

LOG = logging.getLogger(__name__)


class WsprUploader:
    def __init__(
        self,
        credentials: Dict[str, str] | None = None,
        queue_path: str | Path | None = None,
    ) -> None:
        self.credentials = credentials or {}
        self.queue_path = Path(queue_path) if queue_path is not None else Path("./data/wspr_upload_queue.jsonl")
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

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
        """Upload a single spot to WSPRNet.

        Default implementation logs and succeeds. Replace with real HTTP
        submission logic when integrating with WSPRnet.
        """
        LOG.info("Uploading spot to WSPRNet (stub): %s", spot)
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

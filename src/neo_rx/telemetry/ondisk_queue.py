"""Simple on-disk FIFO queue for small JSON messages.

Design goals:
- Durable across process restarts (files persisted in a queue directory).
- Atomic enqueue via write+rename.
- Dequeue by consuming the oldest file (lexicographic by name).
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

LOG = logging.getLogger(__name__)


def _utc_ts() -> str:
    # include microseconds to ensure filenames generated within the same
    # second sort in enqueue order
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


class OnDiskQueue:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def enqueue(self, record: dict) -> None:
        """Persist a record atomically to the queue directory."""
        # Write to a temp file then rename
        fname = f"{_utc_ts()}-{uuid.uuid4().hex}.json"
        tmp = self.path / (fname + ".tmp")
        final = self.path / fname
        try:
            tmp.write_text(json.dumps(record, default=str), encoding="utf-8")
            os.replace(tmp, final)
            LOG.debug("Enqueued message to %s", final)
        except Exception:
            LOG.exception("Failed to enqueue message to %s", self.path)
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    def list(self) -> list[Path]:
        files = [p for p in self.path.iterdir() if p.is_file() and p.suffix == ".json"]
        return sorted(files)

    def dequeue_batch(self, limit: int | None = None) -> Iterable[Path]:
        files = self.list()
        if limit is not None:
            files = files[:limit]
        return files

    def remove(self, p: Path) -> None:
        try:
            p.unlink()
        except Exception:
            LOG.exception("Failed to remove queued file %s", p)

    def size(self) -> int:
        return len(self.list())

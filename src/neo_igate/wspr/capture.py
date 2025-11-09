"""Capture orchestration for WSPR (skeleton).

This module will coordinate SDR captures, scheduling, and hand-off to the
decoder. It currently provides a minimal stub useful for wiring into the CLI.
"""

from __future__ import annotations

import logging
from typing import Optional

LOG = logging.getLogger(__name__)


class WsprCapture:
    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}
        self._running = False

    def start(self) -> None:
        LOG.info("Starting WSPR capture (stub)")
        self._running = True

    def stop(self) -> None:
        LOG.info("Stopping WSPR capture (stub)")
        self._running = False

    def is_running(self) -> bool:
        return self._running

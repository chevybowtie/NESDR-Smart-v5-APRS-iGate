"""WSPR decoder wrapper (skeleton).

This module will wrap an external decoder (eg. wsprd) or a library binding
and emit parsed spots. For now it provides a lightweight stub used by the
CLI and unit tests.
"""

from __future__ import annotations

import logging
from typing import Iterable

LOG = logging.getLogger(__name__)


class WsprDecoder:
    def __init__(self, options: dict | None = None) -> None:
        self.options = options or {}

    def decode_stream(self, iq_stream: Iterable[bytes]) -> Iterable[dict]:
        """Decode an iterable of IQ chunks and yield spot dictionaries.

        This is a stub implementation that yields no spots.
        """
        LOG.debug("WsprDecoder.decode_stream called (stub)")
        if False:
            yield {}

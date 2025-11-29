"""Telemetry publisher abstraction used by optional modules (e.g. WSPR).

Provide a minimal interface that other modules can depend on. Implementations
live alongside this file (eg. `mqtt_publisher.py`).
"""

from __future__ import annotations

from typing import Protocol


class Publisher(Protocol):
    """Minimal publisher interface.

    Implementations should be lightweight and thread-safe where possible.
    """

    def connect(self) -> None:  # pragma: no cover - interface
        ...

    def publish(
        self, topic: str, payload: dict
    ) -> None:  # pragma: no cover - interface
        ...

    def close(self) -> None:  # pragma: no cover - interface
        ...


__all__ = ["Publisher"]

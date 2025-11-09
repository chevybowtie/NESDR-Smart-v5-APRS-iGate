"""MQTT publisher implementation using paho-mqtt.

This module provides a concrete Publisher suitable for lightweight
dashboarding and message-bus publication. The import of `paho.mqtt.client`
is optional; the module will raise ImportError at construction time if the
dependency is missing. This keeps the core project free of hard dependency
unless MQTT is used.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .publisher import Publisher

try:
    import paho.mqtt.client as mqtt  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    mqtt = None  # type: ignore[assignment]

LOG = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(self, host: str = "127.0.0.1", port: int = 1883) -> None:
        if mqtt is None:
            raise ImportError("paho-mqtt is required for MqttPublisher")
        self._host = host
        self._port = port
        self._client = mqtt.Client()

    def connect(self) -> None:
        LOG.debug("Connecting to MQTT broker %s:%s", self._host, self._port)
        self._client.connect(self._host, self._port)

    def publish(self, topic: str, payload: dict) -> None:
        body = json.dumps(payload, default=str)
        LOG.debug("Publishing to %s: %s", topic, body)
        self._client.publish(topic, body)

    def close(self) -> None:
        try:
            self._client.disconnect()
        except Exception:  # pragma: no cover - best-effort cleanup
            LOG.exception("Failed to disconnect MQTT client")


__all__ = ["MqttPublisher"]

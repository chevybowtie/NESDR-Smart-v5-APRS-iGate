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
import random
import time

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
        self._connected = False
        # wire basic callbacks to track connection state
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        # connection retry policy
        self._max_retries = 5
        self._initial_backoff = 0.5  # seconds
        self._max_backoff = 30.0  # seconds

    def connect(self) -> None:
        LOG.debug("Connecting to MQTT broker %s:%s", self._host, self._port)
        self._attempt_connect()
        # start network loop to process callbacks
        try:
            self._client.loop_start()
        except Exception:
            LOG.exception("Failed to start MQTT network loop")

    def publish(self, topic: str, payload: dict) -> None:
        body = json.dumps(payload, default=str)
        LOG.debug("Publishing to %s: %s", topic, body)
        # ensure we are connected (attempt reconnect with backoff if needed)
        if not self._connected:
            LOG.warning("MQTT client not connected; attempting reconnect before publish")
            try:
                self._attempt_connect()
            except Exception:
                LOG.exception("MQTT reconnect failed; dropping publish")
                return

        try:
            self._client.publish(topic, body)
        except Exception:
            LOG.exception("Publish failed; attempting reconnect and retry")
            try:
                self._attempt_connect()
                self._client.publish(topic, body)
            except Exception:
                LOG.exception("Publish retry failed; giving up")

    def close(self) -> None:
        try:
            try:
                self._client.loop_stop()
            except Exception:
                pass
            self._client.disconnect()
        except Exception:  # pragma: no cover - best-effort cleanup
            LOG.exception("Failed to disconnect MQTT client")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:  # pragma: no cover - callback
        if rc == 0:
            LOG.info("MQTT connected to %s:%s", self._host, self._port)
            self._connected = True
        else:
            LOG.warning("MQTT connect returned rc=%s", rc)

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:  # pragma: no cover - callback
        LOG.info("MQTT disconnected (rc=%s)", rc)
        self._connected = False

    def _attempt_connect(self) -> None:
        """Attempt to connect using exponential backoff. Raises on failure."""
        backoff = self._initial_backoff
        for attempt in range(1, self._max_retries + 1):
            try:
                self._client.connect(self._host, self._port)
                # give a short moment for on_connect to be called via loop
                # if loop isn't started yet, perform a small sleep
                time.sleep(0.1)
                if self._connected:
                    return
                # if not yet connected, wait a bit and check
                time.sleep(min(backoff, self._max_backoff))
                if self._connected:
                    return
                raise RuntimeError("Connect did not complete yet")
            except Exception as exc:
                LOG.warning("MQTT connect attempt %d failed: %s", attempt, exc)
                if attempt == self._max_retries:
                    LOG.error("MQTT connect failed after %d attempts", attempt)
                    raise
                # jittered backoff
                jitter = random.uniform(0, backoff * 0.1)
                sleep_for = min(self._max_backoff, backoff + jitter)
                time.sleep(sleep_for)
                backoff = min(self._max_backoff, backoff * 2)


__all__ = ["MqttPublisher"]

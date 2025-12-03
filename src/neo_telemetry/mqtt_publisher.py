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
from typing import Any, Optional
from pathlib import Path
import random
import time as _time

from .ondisk_queue import OnDiskQueue

try:
    import paho.mqtt.client as mqtt  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    mqtt = None  # type: ignore[assignment]

# Allow tests to monkeypatch via neo_rx.telemetry.mqtt_publisher
try:  # pragma: no cover - shim may not be present
    from neo_rx.telemetry import mqtt_publisher as shim
except Exception:
    shim = None  # type: ignore[assignment]


LOG = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        buffer_dir: Optional[Path] = None,
        max_buffer_size: int = 10000,
    ) -> None:
        client_ns = getattr(shim, "mqtt", None) or mqtt
        time_ns = getattr(shim, "time", None) or _time
        if client_ns is None:
            raise ImportError("paho-mqtt is required for MqttPublisher")
        self._host = host
        self._port = port
        self._client = client_ns.Client()
        self._time = time_ns
        self._connected = False
        self.topic: Optional[str] = None  # Default topic for publishing
        # wire basic callbacks to track connection state
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        # connection retry policy
        self._max_retries = 5
        self._initial_backoff = 0.5  # seconds
        self._max_backoff = 30.0  # seconds

        # on-disk FIFO queue (durable)
        self._buffer_dir = buffer_dir or self._default_buffer_dir()
        self._queue_dir = self._buffer_dir / "queue"
        self._max_buffer_size = max_buffer_size
        self._queue = OnDiskQueue(self._queue_dir)
        # ensure on-disk queue directory exists
        self._ensure_buffer_dir()

    def connect(self) -> None:
        LOG.debug("Connecting to MQTT broker %s:%s", self._host, self._port)
        # Start network loop first so on_connect can fire during connect
        try:
            self._client.loop_start()
        except Exception:
            LOG.exception("Failed to start MQTT network loop")
        # Attempt connect with backoff, relying on on_connect to set state
        self._attempt_connect()

    def publish(self, topic: str, payload: dict) -> None:
        body = json.dumps(payload, default=str)
        LOG.debug("Publishing to %s: %s", topic, body)
        # ensure we are connected (attempt reconnect with backoff if needed)
        if not self._connected:
            LOG.warning(
                "MQTT client not connected; enqueueing message to on-disk queue"
            )
            self._enqueue_message(topic, body)
            return

        try:
            self._client.publish(topic, body)
        except Exception:
            LOG.exception("Publish failed; attempting reconnect and retry")
            try:
                self._attempt_connect()
                self._client.publish(topic, body)
            except Exception:
                LOG.exception("Publish retry failed; buffering message")
                # enqueue to durable queue on failure
                self._enqueue_message(topic, body)

    def close(self) -> None:
        try:
            try:
                self._client.loop_stop()
            except Exception:
                pass
            self._client.disconnect()
        except Exception:  # pragma: no cover - best-effort cleanup
            LOG.exception("Failed to disconnect MQTT client")

    def _on_connect(
        self, client: Any, userdata: Any, flags: Any, rc: int
    ) -> None:  # pragma: no cover - callback
        if rc == 0:
            LOG.info("MQTT connected to %s:%s", self._host, self._port)
            self._connected = True
            # drain buffer on successful connection
            self._drain_buffer()
        else:
            LOG.warning("MQTT connect returned rc=%s", rc)

    def _on_disconnect(
        self, client: Any, userdata: Any, rc: int
    ) -> None:  # pragma: no cover - callback
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
                self._time.sleep(0.1)
                if self._connected:
                    return
                # if not yet connected, wait a bit and check
                self._time.sleep(min(backoff, self._max_backoff))
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
                self._time.sleep(sleep_for)
                backoff = min(self._max_backoff, backoff * 2)

    def _default_buffer_dir(self) -> Path:
        """Return default buffer directory using XDG_STATE_HOME or fallback."""
        import os

        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            return Path(xdg_state) / "neo_rx" / "mqtt"
        home = Path.home()
        return home / ".local" / "state" / "neo_rx" / "mqtt"

    def _ensure_buffer_dir(self) -> None:
        """Ensure buffer directory exists."""
        try:
            self._buffer_dir.mkdir(parents=True, exist_ok=True)
            self._queue_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            LOG.exception("Failed to create buffer directory %s", self._buffer_dir)

    def _enqueue_message(self, topic: str, body: str) -> None:
        try:
            if self._queue.size() >= self._max_buffer_size:
                LOG.warning(
                    "MQTT queue at capacity (%d messages); dropping oldest",
                    self._max_buffer_size,
                )
                # remove oldest file to make room
                files = self._queue.list()
                if files:
                    try:
                        self._queue.remove(files[0])
                    except Exception:
                        LOG.exception("Failed to drop oldest queued message")
            record = {"topic": topic, "body": body, "ts": self._time.time()}
            self._queue.enqueue(record)
        except Exception:
            LOG.exception("Failed to enqueue message to on-disk queue")

    def _drain_buffer(self) -> None:
        """Attempt to send all buffered messages."""
        files = self._queue.list()
        if not files:
            return
        try:
            LOG.info("Draining %d queued MQTT messages", len(files))
            failed = []
            for p in files:
                try:
                    text = p.read_text(encoding="utf-8")
                    record = json.loads(text)
                    topic = record.get("topic")
                    body = record.get("body")
                    self._client.publish(topic, body)
                    # remove on success
                    self._queue.remove(p)
                except Exception:
                    LOG.exception(
                        "Failed to publish queued message %s; leaving in queue", p
                    )
                    failed.append(p)
            if failed:
                LOG.info("Left %d messages in queue after drain", len(failed))
            else:
                LOG.info("Queue drained successfully")
        except Exception:
            LOG.exception("Failed to drain on-disk queue")


__all__ = ["MqttPublisher"]

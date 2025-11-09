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
import time

from .publisher import Publisher

try:
    import paho.mqtt.client as mqtt  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    mqtt = None  # type: ignore[assignment]

LOG = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        buffer_dir: Optional[Path] = None,
        max_buffer_size: int = 10000,
    ) -> None:
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

        # on-disk buffering
        self._buffer_dir = buffer_dir or self._default_buffer_dir()
        self._max_buffer_size = max_buffer_size
        self._buffer_file = self._buffer_dir / "mqtt_buffer.jsonl"
        self._ensure_buffer_dir()

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
            LOG.warning("MQTT client not connected; buffering message")
            self._buffer_message(topic, body)
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
                self._buffer_message(topic, body)

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
            # drain buffer on successful connection
            self._drain_buffer()
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

    def _default_buffer_dir(self) -> Path:
        """Return default buffer directory using XDG_STATE_HOME or fallback."""
        import os

        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            return Path(xdg_state) / "neo_igate" / "mqtt"
        home = Path.home()
        return home / ".local" / "state" / "neo_igate" / "mqtt"

    def _ensure_buffer_dir(self) -> None:
        """Ensure buffer directory exists."""
        try:
            self._buffer_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            LOG.exception("Failed to create buffer directory %s", self._buffer_dir)

    def _buffer_message(self, topic: str, body: str) -> None:
        """Write a failed message to the buffer file."""
        try:
            # check buffer size limit
            if self._buffer_file.exists():
                line_count = sum(1 for _ in self._buffer_file.open("r"))
                if line_count >= self._max_buffer_size:
                    LOG.warning(
                        "MQTT buffer at capacity (%d messages); dropping oldest",
                        self._max_buffer_size,
                    )
                    # rotate: keep last (max-1) lines
                    self._rotate_buffer()

            with self._buffer_file.open("a") as f:
                record = {"topic": topic, "body": body, "ts": time.time()}
                f.write(json.dumps(record) + "\n")
            LOG.debug("Buffered message to %s", self._buffer_file)
        except Exception:
            LOG.exception("Failed to buffer message to disk")

    def _rotate_buffer(self) -> None:
        """Remove oldest message from buffer to stay within size limit."""
        try:
            lines = self._buffer_file.read_text().splitlines()
            # keep last (max-1) lines
            keep = lines[-(self._max_buffer_size - 1) :]
            self._buffer_file.write_text("\n".join(keep) + "\n" if keep else "")
        except Exception:
            LOG.exception("Failed to rotate buffer file")

    def _drain_buffer(self) -> None:
        """Attempt to send all buffered messages."""
        if not self._buffer_file.exists():
            return
        try:
            lines = self._buffer_file.read_text().splitlines()
            if not lines:
                return
            LOG.info("Draining %d buffered MQTT messages", len(lines))
            failed = []
            for line in lines:
                try:
                    record = json.loads(line)
                    topic = record["topic"]
                    body = record["body"]
                    self._client.publish(topic, body)
                except Exception:
                    LOG.exception("Failed to publish buffered message; re-buffering")
                    failed.append(line)
            # rewrite buffer with failed messages only
            LOG.debug("Drain complete: %d succeeded, %d failed", len(lines) - len(failed), len(failed))
            if failed:
                self._buffer_file.write_text("\n".join(failed) + "\n")
                LOG.info("Re-buffered %d failed messages", len(failed))
            else:
                # clear buffer
                self._buffer_file.unlink()
                LOG.info("Buffer drained successfully")
        except Exception:
            LOG.exception("Failed to drain buffer")


__all__ = ["MqttPublisher"]

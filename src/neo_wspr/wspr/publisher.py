"""WSPR publisher helpers — bridge to project's telemetry publisher.

This module provides a convenience function to create a publisher based on
the project's configuration. It intentionally avoids hard import of optional
MQTT dependency until actually constructing an MQTT publisher.
"""

from __future__ import annotations

import logging

from neo_rx import config as config_module

LOG = logging.getLogger(__name__)


def make_publisher_from_config(cfg: config_module.StationConfig):
    """Return an instance implementing the Publisher protocol or None.

    If MQTT is enabled in the config, attempt to construct the MQTT
    publisher. If the required dependency is not available, raise
    ImportError.
    """
    if not cfg.mqtt_enabled:
        LOG.debug("MQTT disabled in config; no publisher created")
        return None
    try:
        from neo_telemetry.mqtt_publisher import MqttPublisher

        host = cfg.mqtt_host or "127.0.0.1"
        port = int(cfg.mqtt_port or 1883)
        return MqttPublisher(host=host, port=port)
    except Exception as exc:  # pragma: no cover - optional dep
        LOG.exception("Failed to create MQTT publisher: %s", exc)
        raise

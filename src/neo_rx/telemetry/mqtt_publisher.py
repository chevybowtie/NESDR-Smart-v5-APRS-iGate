"""Backward compatibility shim for MQTT publisher.

This module re-exports from neo_telemetry to maintain backward compatibility.
Also exposes `time` and `mqtt` attributes expected by legacy tests for
monkeypatching.
"""

from neo_telemetry import mqtt_publisher as _impl
from neo_telemetry.mqtt_publisher import MqttPublisher  # re-export

# Expose time so tests can monkeypatch sleep
import time  # noqa: F401

# Expose mqtt client namespace to allow monkeypatching Client in tests
try:  # pragma: no cover - optional dependency
    import paho.mqtt.client as mqtt  # type: ignore[import]
except Exception:
    mqtt = None  # type: ignore[assignment]

# Ensure underlying implementation sees our exposed monkeypatch targets
_impl.time = time  # type: ignore[assignment]
_impl.mqtt = mqtt  # type: ignore[assignment]

__all__ = ["MqttPublisher", "time", "mqtt"]

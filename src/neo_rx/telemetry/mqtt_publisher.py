"""Backward compatibility shim for MQTT publisher.

This module re-exports from neo_telemetry to maintain backward compatibility.
"""

from neo_telemetry.mqtt_publisher import *  # noqa: F401,F403

__all__ = ["MqttPublisher"]

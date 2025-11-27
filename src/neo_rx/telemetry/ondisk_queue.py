"""Backward compatibility shim for on-disk queue.

This module re-exports from neo_telemetry to maintain backward compatibility.
"""

from neo_telemetry.ondisk_queue import *  # noqa: F401,F403

__all__ = ["OnDiskQueue"]

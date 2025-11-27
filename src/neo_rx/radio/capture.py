"""Backward compatibility shim for radio capture utilities.

This module re-exports the capture implementation from neo_core.radio.capture
to maintain backward compatibility during the multi-package migration.
"""

from neo_core.radio.capture import *  # noqa: F401,F403

__all__ = [
    "AudioCaptureError",
    "RtlFmAudioCapture",
    "RtlFmConfig",
]

"""WSPR feature package.

This package contains modules responsible for capturing, decoding,
diagnostics, calibration, and reporting of WSPR spots. Core pipeline
components (capture, decoding, calibration, queueing) are implemented
in a minimal, testable form and can be extended for tighter hardware or
API integrations.
"""

__all__ = [
    "capture",
    "decoder",
    "diagnostics",
    "uploader",
    "calibrate",
    "publisher",
]

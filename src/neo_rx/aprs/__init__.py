"""Back-compat shim re-exporting APRS protocol stack from neo_aprs.

This module remains so existing imports (neo_rx.aprs.*) continue to work
while the refactor progresses. New code should import from neo_aprs.aprs.
"""

from neo_aprs.aprs import (  # noqa: F401,F403
    AX25DecodeError,
    kiss_payload_to_tnc2,
    KISSClient,
    KISSClientConfig,
    KISSClientError,
    KISSFrame,
    KISSCommand,
    APRSISClient,
    APRSISClientError,
    APRSISConfig,
)

__all__ = [
    "AX25DecodeError",
    "kiss_payload_to_tnc2",
    "KISSClient",
    "KISSClientConfig",
    "KISSClientError",
    "KISSFrame",
    "KISSCommand",
    "APRSISClient",
    "APRSISClientError",
    "APRSISConfig",
]

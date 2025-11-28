"""Back-compat shim re-exporting from neo_wspr.wspr."""

# Re-export submodules by name to avoid star-import issues
from neo_wspr.wspr import (
    capture,
    decoder,
    diagnostics,
    uploader,
    calibrate,
    publisher,
    scan,
)

__all__ = [
    "capture",
    "decoder",
    "diagnostics",
    "uploader",
    "calibrate",
    "publisher",
    "scan",
]

"""WSPRNet uploader (skeleton).

Handles optional, opt-in upload of decoded spots to wsprnet.org. This is a
placeholder implementation; actual HTTP endpoints and authentication
mechanisms will be implemented when integrating with a concrete uploader
strategy.
"""

from __future__ import annotations

import logging
from typing import Dict

LOG = logging.getLogger(__name__)


class WsprUploader:
    def __init__(self, credentials: Dict[str, str] | None = None) -> None:
        self.credentials = credentials or {}

    def upload_spot(self, spot: Dict) -> bool:
        LOG.info("Uploading spot to WSPRNet (stub): %s", spot)
        return True

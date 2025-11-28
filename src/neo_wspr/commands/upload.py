"""WSPR upload command implementation.

Drains the queued spots to WSPRNet.
"""

from __future__ import annotations

import json
import logging
from argparse import Namespace

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_upload(args: Namespace) -> int:
    """Upload queued WSPR spots to WSPRNet."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.error(
            "Cannot upload WSPR spots without a configuration; rerun neo-rx setup or provide --config"
        )
        return 1

    if not getattr(cfg, "wspr_uploader_enabled", False):
        LOG.error(
            "WSPR uploader is disabled. Set wspr_uploader_enabled = true in config.toml before uploading"
        )
        return 1

    data_dir = config_module.get_mode_data_dir("wspr")
    queue_path = data_dir / "wspr_upload_queue.jsonl"

    LOG.info("Requested WSPR upload")

    from neo_wspr.wspr.uploader import WsprUploader

    try:
        uploader = WsprUploader(queue_path=queue_path)

        # Optional heartbeat prior to draining queue
        if getattr(args, "heartbeat", False):
            try:
                uploader.send_heartbeat(callsign=getattr(cfg, "callsign", None))
            except Exception:
                LOG.exception("Heartbeat send failed; continuing to drain queue")

        result = uploader.drain()
        LOG.info(
            "Upload drain complete: attempted=%d succeeded=%d failed=%d",
            result.get("attempted", 0),
            result.get("succeeded", 0),
            result.get("failed", 0),
        )
        last_error = result.get("last_error")
        if last_error:
            LOG.warning("Last WSPR upload error: %s", last_error)

        # Emit JSON if requested
        if getattr(args, "json", False):
            if getattr(args, "heartbeat", False):
                try:
                    # Mark that heartbeat was sent for JSON output expectations
                    result["heartbeat_sent"] = True
                except Exception:
                    pass
            result.setdefault("last_error", None)
            print(json.dumps(result, indent=2))

        return 0
    except Exception:
        LOG.exception("Upload operation failed")
        return 1

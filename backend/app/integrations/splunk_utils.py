"""Splunk HTTP Event Collector client (req.md Sec. 37)."""
import logging
import time

import httpx

from ..config import settings

logger = logging.getLogger("churnplatform.splunk")


def send_event(event_type: str, payload: dict) -> bool:
    """Best-effort delivery — Splunk must never be a hard dependency for serving."""
    body = {
        "index": settings.splunk_index,
        "sourcetype": "_json",
        "event": {"event_type": event_type, "timestamp": time.time(), **payload},
    }
    try:
        resp = httpx.post(
            settings.splunk_hec_url,
            json=body,
            headers={"Authorization": f"Splunk {settings.splunk_hec_token}"},
            verify=settings.splunk_verify_tls,
            timeout=3.0,
        )
        return resp.status_code == 200
    except Exception:
        logger.warning("Splunk HEC delivery failed for event_type=%s", event_type, exc_info=True)
        return False

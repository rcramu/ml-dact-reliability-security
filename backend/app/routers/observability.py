"""Prometheus scrape endpoint + seed-scenario listing for the monitoring pipeline."""
from fastapi import APIRouter, Response

from ..integrations.prometheus_metrics import latest_metrics

router = APIRouter(tags=["Observability"])


@router.get("/metrics", summary="Prometheus scrape endpoint (req.md Sec. 11)")
def metrics():
    payload, content_type = latest_metrics()
    return Response(content=payload, media_type=content_type)


@router.get("/observability/seed-profiles", summary="List the seedable production-traffic profiles for drift checks")
def profiles():
    return {
        "profiles": [
            {"id": "stable", "description": "Production traffic still matches the training distribution — expect LOW drift."},
            {"id": "drifted", "description": "Moderate distribution shift (more support tickets, lower engagement) — expect WARNING/HIGH drift."},
            {"id": "severe_drift", "description": "Severe distribution shift + noisier labels — expect CRITICAL drift and likely an automatic retrain."},
        ]
    }

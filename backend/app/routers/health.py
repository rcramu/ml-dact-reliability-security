"""Liveness/readiness probes for docker-compose healthchecks."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness probe")
def health():
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe — DB connectivity + fleet seeding status")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    models_count = db.query(models.TrainedModel).count()
    versions_count = db.query(models.ModelVersion).count()
    runs_count = db.query(models.PipelineRun).count()
    return {
        "database": True,
        "models_seeded": models_count,
        "versions_seeded": versions_count,
        "pipeline_runs_seeded": runs_count,
        "ready": models_count > 0 and versions_count > 0,
    }

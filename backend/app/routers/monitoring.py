"""Drift detection + decision matrix API (req.md Sec. 11-13) — the feedback loop."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models as m
from .. import monitoring_engine as mon
from .. import schemas
from .. import serializers as ser
from ..database import get_db

router = APIRouter(prefix="/api/v1/models", tags=["Drift & Monitoring"])


def _get_model(db: Session, name: str) -> m.TrainedModel:
    model = db.query(m.TrainedModel).filter_by(name=name).one_or_none()
    if model is None:
        raise HTTPException(404, f"model '{name}' not found")
    return model


@router.post("/{model}/monitoring/check", summary="Run a drift + evaluation check against production traffic (req.md Sec. 11-13)")
def trigger_check(model: str, body: schemas.DriftCheckRequest, db: Session = Depends(get_db)):
    trained_model = _get_model(db, model)
    try:
        check = mon.run_monitoring_check(db, trained_model, profile=body.profile, auto_retrain=body.auto_retrain)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return ser.drift_check_dict(check, include_features=True)


@router.get("/{model}/monitoring/history", summary="Drift check history for a model")
def check_history(model: str, db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    trained_model = _get_model(db, model)
    rows = (
        db.query(m.DriftCheck).filter_by(model_id=trained_model.id)
        .order_by(m.DriftCheck.created_at.desc()).limit(limit).all()
    )
    return [ser.drift_check_dict(c) for c in rows]


@router.get("/{model}/monitoring/{check_id}", summary="Drift check detail — every feature's PSI/KS result")
def check_detail(model: str, check_id: str, db: Session = Depends(get_db)):
    trained_model = _get_model(db, model)
    check = db.query(m.DriftCheck).filter_by(id=check_id, model_id=trained_model.id).one_or_none()
    if check is None:
        raise HTTPException(404, "drift check not found")
    return ser.drift_check_dict(check, include_features=True)


@router.get("/{model}/monitoring/decision-matrix", summary="The 6-outcome drift/evaluation decision matrix (req.md Sec. 13)")
def decision_matrix_table():
    from ..ml.decision_matrix import DECISION_MATRIX
    return [
        {"drift_level": d, "evaluation_level": e, "overall_status": status, "recommended_action": action}
        for (d, e), (status, action) in DECISION_MATRIX.items()
    ]

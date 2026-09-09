"""Real-time inference API (req.md Sec. 10) — POST /predict against the current
production champion, logging telemetry consumed by drift detection, Prometheus,
and Splunk."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from .. import predictor
from .. import schemas
from .. import serializers as ser
from ..database import get_db
from ..integrations import splunk_utils
from ..integrations.prometheus_metrics import record_prediction

router = APIRouter(prefix="/api/v1/models", tags=["Prediction"])


@router.post("/{model}/predict", summary="Score a customer against the current production champion (req.md Sec. 10)")
def predict(model: str, body: schemas.PredictRequest, db: Session = Depends(get_db)):
    trained_model = db.query(m.TrainedModel).filter_by(name=model).one_or_none()
    if trained_model is None:
        raise HTTPException(404, f"model '{model}' not found")
    champion = db.query(m.ModelVersion).filter_by(model_id=trained_model.id, is_champion=True).one_or_none()
    if champion is None:
        raise HTTPException(409, f"'{model}' has no production champion yet — trigger a training run first")

    features = body.model_dump()
    try:
        prob, prediction, latency_ms = predictor.score_record(db, champion, features)
    except Exception as exc:  # pragma: no cover
        record_prediction(model, str(champion.version), probability=0.0, latency_seconds=0.0, error=True)
        raise HTTPException(500, f"inference failed: {exc}")

    row = m.ProductionPrediction(
        model_version_id=champion.id, **features,
        churn_probability=round(prob, 4), prediction=prediction, latency_ms=round(latency_ms, 3), profile="live",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    record_prediction(model, str(champion.version), probability=prob, latency_seconds=latency_ms / 1000.0)
    splunk_utils.send_event("prediction", {"model": model, "version": champion.version, "prediction": prediction, "probability": prob})

    return {
        "prediction": prediction,
        "churn_probability": round(prob, 4),
        "model_version": champion.version,
        "decision_threshold": champion.decision_threshold,
        "latency_ms": round(latency_ms, 3),
        "request_id": row.request_id,
    }


@router.get("/{model}/predict/history", summary="Browse recent live /predict calls")
def predict_history(model: str, db: Session = Depends(get_db), limit: int = 100):
    trained_model = db.query(m.TrainedModel).filter_by(name=model).one_or_none()
    if trained_model is None:
        raise HTTPException(404, f"model '{model}' not found")
    version_ids = [v.id for v in db.query(m.ModelVersion.id).filter_by(model_id=trained_model.id).all()]
    rows = (
        db.query(m.ProductionPrediction)
        .filter(m.ProductionPrediction.model_version_id.in_(version_ids))
        .order_by(m.ProductionPrediction.created_at.desc()).limit(limit).all()
    ) if version_ids else []
    return [ser.production_prediction_dict(p) for p in rows]

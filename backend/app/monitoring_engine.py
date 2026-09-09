"""The monitoring pipeline (req.md Sec. 11-13) — the feedback loop.

Compares the current production champion's TRAINING distribution (reference)
against a simulated batch of live scoring traffic (production), computes
PSI/KS per feature, combines that with a production-performance evaluation
via the drift+evaluation decision matrix, and — only when drift is HIGH AND
the model's evaluated quality is not confirmed GOOD — automatically triggers
a new training pipeline run (req.md Sec. 13's "Drift > threshold? -> Airflow
Trigger -> Training DAG").
"""
import logging

from sqlalchemy.orm import Session

from . import data_generator as gen
from . import models as m
from . import pipeline_engine as pe
from .config import settings
from .integrations import splunk_utils
from .integrations.prometheus_metrics import record_drift
from .ml import decision_matrix
from .ml.drift import feature_status, ks_test, psi_numeric
from .predictor import get_or_train
from .ml.pytorch_trainer import predict

logger = logging.getLogger("churnplatform.monitoring")

FEATURE_NAMES = gen.FEATURE_NAMES


def _reference_arrays(db: Session, champion: m.ModelVersion) -> dict:
    records = (
        db.query(m.RawRecord).filter_by(dataset_version_id=champion.dataset_version_id).all()
    )
    dicts = [{
        "tenure_months": r.tenure_months, "monthly_charges": r.monthly_charges, "age": r.age,
        "support_tickets_90d": r.support_tickets_90d, "usage_hours_week": r.usage_hours_week,
        "is_month_to_month": r.is_month_to_month, "autopay_enabled": r.autopay_enabled, "has_addons": r.has_addons,
    } for r in records]
    return gen.feature_matrix(dicts)


def run_monitoring_check(db: Session, model: m.TrainedModel, *, profile: str = "stable", auto_retrain: bool = True, seed: int | None = None) -> m.DriftCheck:
    champion = db.query(m.ModelVersion).filter_by(model_id=model.id, is_champion=True).one_or_none()
    if champion is None:
        raise ValueError(f"{model.name} has no production champion to monitor yet")

    check_seed = seed if seed is not None else gen.stable_seed(f"{model.name}:monitor:{profile}:{champion.id}")
    production_records = gen.generate_production_batch(profile, check_seed, n=250)

    reference = _reference_arrays(db, champion)
    production = gen.feature_matrix(production_records)

    drift_check = m.DriftCheck(model_id=model.id, model_version_id=champion.id)
    db.add(drift_check)
    db.flush()

    max_psi = 0.0
    worst_feature = None
    for name in FEATURE_NAMES:
        psi = psi_numeric(reference[name], production[name])
        ks_stat, ks_p = ks_test(reference[name], production[name])
        status = feature_status(psi, settings.psi_warning, settings.psi_critical)
        db.add(m.DriftFeatureResult(
            drift_check_id=drift_check.id, feature_name=name, psi=round(psi, 4),
            ks_statistic=round(ks_stat, 4), ks_pvalue=round(ks_p, 4),
            reference_mean=round(float(reference[name].mean()), 4),
            production_mean=round(float(production[name].mean()), 4),
            status=status,
        ))
        if psi > max_psi:
            max_psi, worst_feature = psi, name

    overall_psi_status = feature_status(max_psi, settings.psi_warning, settings.psi_critical)
    drift_level = "HIGH" if overall_psi_status in ("WARNING", "CRITICAL") else "LOW"

    # Production performance signal (req.md Sec. 13 "drift alone doesn't indicate failure")
    trained, threshold = get_or_train(db, champion)
    x_prod, y_prod = gen.production_records_to_arrays(production_records)
    probs = predict(trained, x_prod)
    preds = (probs >= threshold).astype(int)
    production_accuracy = float((preds == y_prod).mean()) if len(y_prod) else None

    evaluation_level = "UNKNOWN"
    if production_accuracy is not None and champion.accuracy:
        delta = champion.accuracy - production_accuracy
        if delta <= 0.05:
            evaluation_level = "GOOD"
        elif delta >= 0.15:
            evaluation_level = "BAD"
        else:
            evaluation_level = "UNKNOWN"

    overall_status, recommended_action = decision_matrix.decide(drift_level, evaluation_level)
    should_retrain = auto_retrain and decision_matrix.should_retrain(drift_level, evaluation_level)

    drift_check.drift_level = drift_level
    drift_check.evaluation_level = evaluation_level
    drift_check.overall_status = overall_status
    drift_check.recommended_action = recommended_action
    drift_check.max_psi = round(max_psi, 4)
    drift_check.production_accuracy = round(production_accuracy, 4) if production_accuracy is not None else None
    db.flush()

    record_drift(model.name, max_psi)

    if overall_status in ("WARNING", "CRITICAL"):
        db.add(m.Alert(
            model_version_id=champion.id, category="drift_detected",
            severity="CRITICAL" if overall_status == "CRITICAL" else "WARNING", channel="slack",
            message=f"{model.name} v{champion.version}: drift check -> {overall_status} "
                    f"(max PSI={max_psi:.3f} on '{worst_feature}', evaluation={evaluation_level}). {recommended_action}.",
        ))
        splunk_utils.send_event("drift_check", {
            "model": model.name, "version": champion.version, "drift_level": drift_level,
            "evaluation_level": evaluation_level, "overall_status": overall_status, "max_psi": max_psi,
        })

    if should_retrain:
        run = pe.run_pipeline(
            db, model, trigger_type="drift",
            trigger_detail=f"Automatic retrain: PSI={max_psi:.3f} on '{worst_feature}' (drift={drift_level}, evaluation={evaluation_level})",
            scenario="feature_drift",
        )
        drift_check.triggered_retrain = True
        drift_check.retrain_run_id = run.id
        db.add(m.Alert(
            model_version_id=champion.id, category="auto_retrain_triggered", severity="WARNING", channel="slack",
            message=f"{model.name}: drift-triggered retraining started automatically (run {run.id}).",
        ))

    db.commit()
    db.refresh(drift_check)
    return drift_check

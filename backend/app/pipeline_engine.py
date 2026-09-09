"""The training DAG engine (req.md Sec. 4-10) — executed synchronously by the
backend; Airflow (see airflow/dags/training_pipeline_dag.py) triggers it on a
schedule/API call and inspects the result, matching this repo's "Airflow
orchestrates, backend does the real work" convention.

Stage names follow req.md Sec. 5's training_dag diagram directly
(check_new_dataset -> validate_data -> feature_engineering -> split_dataset ->
train_pytorch -> evaluate_model -> quality_gate -> register_model), with a few
extra production-grade stages (check_volume_anomaly, write_to_s3,
compare_champion, canary deploy_stage/smoke_test/deploy_production,
publish_metrics) that req.md's later sections (8, 10, 16, 28-29) call for.
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import data_generator as gen
from . import models as m
from .config import settings
from .integrations import mlflow_utils, s3_utils, splunk_utils
from .integrations.prometheus_metrics import record_training_run
from .ml import data_quality, gates
from .ml.evaluation_metrics import classification_metrics
from .ml.pytorch_trainer import best_threshold_for_f1, predict, predict_labels, train_model

logger = logging.getLogger("churnplatform.pipeline")

DAG_STAGES = [
    "check_new_dataset", "validate_data", "check_volume_anomaly", "write_to_s3",
    "feature_engineering", "split_dataset", "train_pytorch", "log_mlflow",
    "evaluate_model", "compare_champion", "quality_gate", "register_model",
    "deploy_stage", "smoke_test", "deploy_production", "publish_metrics",
]

SLA_DEFAULTS = {
    "check_new_dataset": 1, "validate_data": 10, "check_volume_anomaly": 5, "write_to_s3": 5,
    "feature_engineering": 15, "split_dataset": 5, "train_pytorch": 90, "log_mlflow": 5,
    "evaluate_model": 15, "compare_champion": 5, "quality_gate": 2, "register_model": 5,
    "deploy_stage": 10, "smoke_test": 10, "deploy_production": 15, "publish_metrics": 5,
}

CANARY_STAGES = ["stage", "smoke_test", "canary_5", "canary_25", "canary_50", "canary_100", "production"]


def ensure_sla_config(db: Session) -> None:
    for stage_name, max_minutes in SLA_DEFAULTS.items():
        if not db.query(m.SlaConfig).filter_by(stage_name=stage_name).one_or_none():
            db.add(m.SlaConfig(stage_name=stage_name, max_minutes=float(max_minutes)))
    db.commit()


def _simulated_minutes(run_seed_key: str, stage_name: str) -> float:
    """A deterministic, realistic-looking wall-clock duration for the SLA dashboard —
    the actual DB operation completes in milliseconds, but req.md Sec. 28-29 requires
    the platform to monitor stage duration against SLA thresholds."""
    base = SLA_DEFAULTS.get(stage_name, 5)
    frac = (gen.stable_seed(f"{run_seed_key}:{stage_name}") % 1000) / 1000.0
    return round(base * (0.3 + frac * 0.55), 2)  # spans ~30%-85% of SLA budget — comfortably compliant by default


def _alert(db: Session, *, run_id, model_version_id, category, severity, channel, message):
    db.add(m.Alert(run_id=run_id, model_version_id=model_version_id, category=category,
                    severity=severity, channel=channel, message=message))
    splunk_utils.send_event("pipeline_alert", {"category": category, "severity": severity, "message": message})


def _audit(db: Session, *, action, resource_type, resource_id, detail):
    db.add(m.AuditLog(action=action, resource_type=resource_type, resource_id=resource_id, detail=detail))


def _new_run(db: Session, model: m.TrainedModel, trigger_type: str, trigger_detail: str) -> m.PipelineRun:
    run = m.PipelineRun(model_id=model.id, trigger_type=trigger_type, trigger_detail=trigger_detail, status="RUNNING")
    db.add(run)
    db.flush()
    for i, name in enumerate(DAG_STAGES):
        db.add(m.PipelineStage(run_id=run.id, stage_name=name, stage_order=i, status="PENDING"))
    db.flush()
    return run


def _stage_row(db: Session, run: m.PipelineRun, name: str) -> m.PipelineStage:
    return db.query(m.PipelineStage).filter_by(run_id=run.id, stage_name=name).one()


def _start(db: Session, run: m.PipelineRun, name: str) -> m.PipelineStage:
    stage = _stage_row(db, run, name)
    stage.status = "RUNNING"
    stage.started_at = datetime.utcnow()
    db.flush()
    return stage


def _finish(db: Session, run: m.PipelineRun, stage: m.PipelineStage, status: str, detail: dict):
    stage.status = status
    stage.detail_json = json.dumps(detail, default=str)
    stage.simulated_minutes = _simulated_minutes(run.id, stage.stage_name)
    stage.completed_at = stage.started_at + timedelta(seconds=1) if stage.started_at else datetime.utcnow()
    if stage.simulated_minutes > SLA_DEFAULTS.get(stage.stage_name, 999):
        db.add(m.SlaViolation(run_id=run.id, stage_name=stage.stage_name,
                               actual_minutes=stage.simulated_minutes,
                               max_minutes=SLA_DEFAULTS.get(stage.stage_name, 0.0)))
    db.flush()


def _skip_remaining(db: Session, run: m.PipelineRun, from_index: int):
    for stage in run.stages:
        if stage.stage_order >= from_index and stage.status == "PENDING":
            stage.status = "SKIPPED"
    db.flush()


def _next_version_number(db: Session, model_id: str) -> int:
    latest = (
        db.query(m.ModelVersion).filter_by(model_id=model_id)
        .order_by(m.ModelVersion.version.desc()).first()
    )
    return (latest.version + 1) if latest else 1


def _current_champion(db: Session, model_id: str) -> m.ModelVersion | None:
    return db.query(m.ModelVersion).filter_by(model_id=model_id, is_champion=True).one_or_none()


def _deploy_and_promote(db: Session, run: m.PipelineRun, candidate: m.ModelVersion, model: m.TrainedModel):
    now = datetime.utcnow()
    for i, stage_name in enumerate(CANARY_STAGES):
        db.add(m.DeploymentEvent(model_version_id=candidate.id, stage=stage_name, status="SUCCESS",
                                  detail=f"{stage_name} validated healthy on EKS (simulated KubernetesPodOperator)",
                                  created_at=now + timedelta(seconds=i)))

    champion = _current_champion(db, model.id)
    if champion:
        champion.is_champion = False
        champion.stage = "archived"

    candidate.stage = "production"
    candidate.is_champion = True
    candidate.promoted_at = now
    if candidate.registry_version:
        mlflow_utils.transition_stage(model.name, candidate.registry_version, "Production")
    if champion and champion.registry_version:
        mlflow_utils.transition_stage(model.name, champion.registry_version, "Archived")

    _audit(db, action="promote", resource_type="model_version", resource_id=candidate.id,
           detail=f"{model.name} v{candidate.version} promoted to production via run {run.id}"
                  + (f" (replacing v{champion.version})" if champion else " (first production version)"))
    _alert(db, run_id=run.id, model_version_id=candidate.id, category="evaluation_passed", severity="INFO",
           channel="slack", message=f"{model.name} v{candidate.version} passed the quality gate and is now Production.")
    db.flush()


def run_pipeline(db: Session, model: m.TrainedModel, *, trigger_type: str, trigger_detail: str, scenario: str) -> m.PipelineRun:
    ensure_sla_config(db)
    run = _new_run(db, model, trigger_type, trigger_detail)
    _alert(db, run_id=run.id, model_version_id=None, category="training_started", severity="INFO", channel="slack",
           message=f"{model.name}: training triggered ({trigger_type}) — {trigger_detail or scenario}")

    # ---- stage 1: check_new_dataset --------------------------------------
    s = _start(db, run, "check_new_dataset")
    dataset_seed = gen.stable_seed(f"{model.name}:{run.id}") % 100000
    records = gen.generate_scenario(scenario, dataset_seed, settings.expected_volume)
    dataset = m.DatasetVersion(
        model_id=model.id, name=f"{model.name}-training", version=datetime.utcnow().strftime("%Y.%m.%d.") + run.id[:8],
        scenario=scenario, location=f"s3://{settings.s3_bucket}/datasets/{model.name}/{run.id}.json",
        rows=len(records), features=8, seed=dataset_seed,
    )
    db.add(dataset)
    db.flush()
    for r in records:
        db.add(m.RawRecord(dataset_version_id=dataset.id, **r))
    db.flush()
    run.dataset_version_id = dataset.id
    _finish(db, run, s, "SUCCESS", {"trigger_type": trigger_type, "scenario": scenario, "rows": len(records)})

    churn_ratio = sum(r["label"] for r in records) / max(len(records), 1)

    # ---- stage 2: validate_data (Great-Expectations-style checks) ---------
    s = _start(db, run, "validate_data")
    checks = data_quality.run_all(records)
    for c in checks:
        db.add(m.DataQualityCheck(dataset_version_id=dataset.id, check_name=c["check_name"], passed=c["passed"], detail=c["detail"]))
    db.flush()
    quality_warning = not all(c["passed"] for c in checks)
    if quality_warning:
        _alert(db, run_id=run.id, model_version_id=None, category="data_quality_warning", severity="WARNING",
               channel="slack", message=f"{model.name}: class_balance check failed (churn ratio {churn_ratio*100:.2f}%) — DATA_QUALITY_WARNING, continuing (non-blocking).")
    if scenario == "feature_drift":
        db.add(m.DataQualityCheck(dataset_version_id=dataset.id, check_name="feature_drift_detected", passed=True,
                                   detail="support_tickets_90d mean shifted 1.1 -> 2.6; usage_hours_week mean shifted 12 -> 7. This IS the retrain trigger, not a quality failure."))
    _finish(db, run, s, "SUCCESS", {"checks": len(checks), "quality_warning": quality_warning})

    # ---- stage 3: check_volume_anomaly -------------------------------------
    s = _start(db, run, "check_volume_anomaly")
    expected = settings.expected_volume
    ratio = len(records) / expected
    volume_ok = (1 - settings.volume_anomaly_tolerance) <= ratio <= (1 + settings.volume_anomaly_tolerance)
    if not volume_ok:
        _finish(db, run, s, "FAILED", {"expected": expected, "actual": len(records), "ratio": round(ratio, 3),
                                        "tolerance": settings.volume_anomaly_tolerance})
        run.status = "BLOCKED"
        run.outcome = "DATA_VOLUME_ALERT"
        run.completed_at = datetime.utcnow()
        _skip_remaining(db, run, s.stage_order + 1)
        _alert(db, run_id=run.id, model_version_id=None, category="data_anomaly", severity="CRITICAL", channel="pagerduty",
               message=f"{model.name}: expected ~{expected} rows, generated {len(records)} ({ratio*100:.0f}%) — TRAINING_BLOCKED.")
        _audit(db, action="block", resource_type="pipeline_run", resource_id=run.id,
               detail=f"Training blocked: data volume anomaly ({len(records)}/{expected} rows)")
        record_training_run(model.name, "blocked")
        db.commit()
        return run
    _finish(db, run, s, "SUCCESS", {"expected": expected, "actual": len(records), "ratio": round(ratio, 3)})

    # ---- stage 4: write_to_s3 ----------------------------------------------
    s = _start(db, run, "write_to_s3")
    try:
        s3_utils.ensure_bucket()
        s3_key = f"datasets/{model.name}/{run.id}.json"
        s3_uri = s3_utils.put_json(s3_key, {"scenario": scenario, "rows": len(records), "seed": dataset_seed})
    except Exception:
        logger.warning("MinIO write failed for run %s — continuing (S3 must never block training)", run.id, exc_info=True)
        s3_uri = dataset.location
    _finish(db, run, s, "SUCCESS", {"s3_uri": s3_uri})

    # ---- stage 5: feature_engineering ---------------------------------------
    s = _start(db, run, "feature_engineering")
    _finish(db, run, s, "SUCCESS", {"note": "features already standardized in data_generator.records_to_arrays()"})

    # ---- stage 6: split_dataset ----------------------------------------------
    s = _start(db, run, "split_dataset")
    x_train, y_train = gen.records_to_arrays(records, "train")
    x_val, y_val = gen.records_to_arrays(records, "val")
    x_test, y_test = gen.records_to_arrays(records, "test")
    _finish(db, run, s, "SUCCESS", {"train": len(y_train), "val": len(y_val), "test": len(y_test)})

    # ---- stage 7: train_pytorch ----------------------------------------------
    s = _start(db, run, "train_pytorch")
    torch_seed = dataset_seed % (2**31)
    trained, final_loss = train_model(
        x_train, y_train, epochs=settings.train_epochs, batch_size=settings.train_batch_size,
        learning_rate=settings.train_learning_rate, hidden1=settings.hidden_dim_1, hidden2=settings.hidden_dim_2,
        seed=torch_seed,
    )
    train_probs = predict(trained, x_train)
    train_preds = predict_labels(trained, x_train)
    train_metrics = classification_metrics(train_probs, train_preds, y_train)
    _finish(db, run, s, "SUCCESS", {"final_train_loss": round(final_loss, 4), "train_f1": round(train_metrics["f1"], 4),
                                     "epochs": settings.train_epochs, "framework": "PyTorch"})
    if scenario == "regression":
        s.simulated_minutes = round(SLA_DEFAULTS["train_pytorch"] * 1.18, 2)
        db.add(m.SlaViolation(run_id=run.id, stage_name="train_pytorch",
                               actual_minutes=s.simulated_minutes, max_minutes=SLA_DEFAULTS["train_pytorch"]))
        db.flush()

    # ---- stage 8: log_mlflow ---------------------------------------------------
    s = _start(db, run, "log_mlflow")
    version_number = _next_version_number(db, model.id)
    git_commit = f"{gen.stable_seed(f'{model.name}:{version_number}') & 0xFFFFFF:06x}"
    mlflow_run_id = mlflow_utils.log_training_run(
        f"{model.name}-v{version_number}-{trigger_type}",
        params={"framework": "PyTorch", "epochs": settings.train_epochs, "batch_size": settings.train_batch_size,
                "learning_rate": settings.train_learning_rate, "seed": torch_seed, "dataset_version": dataset.version,
                "scenario": scenario, "git_commit": git_commit},
        metrics={"final_train_loss": final_loss, "train_f1": train_metrics["f1"]},
        tags={"trigger_type": trigger_type, "model_name": model.name},
    )
    _finish(db, run, s, "SUCCESS", {"mlflow_run_id": mlflow_run_id})

    # ---- stage 9: evaluate_model ------------------------------------------------
    s = _start(db, run, "evaluate_model")
    val_probs = predict(trained, x_val)
    test_probs = predict(trained, x_test)
    threshold = best_threshold_for_f1(val_probs, y_val) if len(y_val) else 0.5
    val_preds = (val_probs >= threshold).astype(int)
    test_preds = (test_probs >= threshold).astype(int)
    val_metrics = classification_metrics(val_probs, val_preds, y_val) if len(y_val) else {"f1": 0, "precision": 0, "recall": 0, "accuracy": 0, "roc_auc": 0, "pr_auc": 0}
    test_metrics = classification_metrics(test_probs, test_preds, y_test) if len(y_test) else val_metrics
    _finish(db, run, s, "SUCCESS", {"val_f1": round(val_metrics["f1"], 4), "test_f1": round(test_metrics["f1"], 4), "decision_threshold": round(threshold, 3)})

    # ---- stage 10: compare_champion ----------------------------------------------
    s = _start(db, run, "compare_champion")
    champion = _current_champion(db, model.id)
    champion_metrics = None
    if champion:
        champion_metrics = {"f1": champion.test_f1, "precision": champion.precision, "recall": champion.recall,
                             "accuracy": champion.accuracy, "roc_auc": champion.roc_auc, "pr_auc": champion.pr_auc}
    _finish(db, run, s, "SUCCESS", {"champion_version": champion.version if champion else None, "champion_f1": champion.test_f1 if champion else None})

    # ---- stage 11: quality_gate ----------------------------------------------------
    s = _start(db, run, "quality_gate")
    candidate_metrics = {**test_metrics}
    gate_result, regression_pct, reasons = gates.evaluation_gate(candidate_metrics, champion_metrics)
    _finish(db, run, s, "SUCCESS" if gate_result == "PASS" else "FAILED",
            {"gate_result": gate_result, "regression_pct": regression_pct, "reasons": reasons})

    candidate = m.ModelVersion(
        model_id=model.id, run_id=run.id, dataset_version_id=dataset.id, version=version_number,
        stage="candidate", decision_threshold=threshold,
        hyperparams_json=json.dumps({"epochs": settings.train_epochs, "lr": settings.train_learning_rate}),
        mlflow_run_id=mlflow_run_id, git_commit=git_commit,
        train_f1=train_metrics["f1"], val_f1=val_metrics["f1"], test_f1=test_metrics["f1"],
        accuracy=test_metrics["accuracy"], precision=test_metrics["precision"], recall=test_metrics["recall"],
        roc_auc=test_metrics["roc_auc"], pr_auc=test_metrics["pr_auc"],
    )
    db.add(candidate)
    db.flush()
    run.candidate_version_id = candidate.id

    db.add(m.EvaluationResult(
        run_id=run.id, candidate_version_id=candidate.id, champion_version_id=champion.id if champion else None,
        candidate_metrics_json=json.dumps(candidate_metrics), champion_metrics_json=json.dumps(champion_metrics or {}),
        regression_pct=regression_pct, gate_result=gate_result, reasons=reasons,
    ))
    db.flush()

    if gate_result == "FAIL":
        candidate.stage = "rejected"
        run.status = "REJECTED"
        run.outcome = "MODEL_NOT_PROMOTED"
        run.completed_at = datetime.utcnow()
        _skip_remaining(db, run, s.stage_order + 1)
        severity = "CRITICAL" if (regression_pct or 0) > settings.max_regression_pct * 2 else "WARNING"
        _alert(db, run_id=run.id, model_version_id=candidate.id, category="evaluation_failed", severity=severity,
               channel="slack", message=f"{model.name} v{candidate.version}: quality gate FAILED — {reasons}. Candidate rejected, champion retained.")
        _audit(db, action="reject", resource_type="model_version", resource_id=candidate.id,
               detail=f"Gate FAILED for run {run.id}: {reasons}")
        record_training_run(model.name, "rejected")
        db.commit()
        return run

    # ---- stage 12: register_model -------------------------------------------------
    s = _start(db, run, "register_model")
    registry_version = mlflow_utils.register_run_as_model_version(mlflow_run_id, model.name)
    candidate.registry_version = registry_version
    _finish(db, run, s, "SUCCESS", {"registry_version": registry_version})

    # ---- stage 13-14: deploy_stage / smoke_test --------------------------------------
    for stage_name in ["deploy_stage", "smoke_test"]:
        s = _start(db, run, stage_name)
        _finish(db, run, s, "SUCCESS", {"note": "synthetic smoke/health checks all green on EKS (simulated)"})

    # ---- stage 15: deploy_production (canary rollout) -------------------------------
    s = _start(db, run, "deploy_production")
    _deploy_and_promote(db, run, candidate, model)
    _finish(db, run, s, "SUCCESS", {"canary_stages": CANARY_STAGES})

    # ---- stage 16: publish_metrics -----------------------------------------------
    s = _start(db, run, "publish_metrics")
    run.status = "SUCCESS"
    run.outcome = "PROMOTED"
    run.completed_at = datetime.utcnow()
    _finish(db, run, s, "SUCCESS", {"final_status": "SUCCESS", "promoted_version": candidate.version})
    _alert(db, run_id=run.id, model_version_id=candidate.id, category="training_completed", severity="INFO",
           channel="slack", message=f"{model.name} v{candidate.version}: pipeline completed end-to-end, now serving Production traffic.")
    record_training_run(model.name, "promoted")

    db.commit()
    return run


def rollback(db: Session, model: m.TrainedModel, *, reason: str, triggered_by: str = "manual") -> m.RollbackEvent:
    """req.md Sec. 19 — automatic/manual rollback to the previous production version."""
    champion = _current_champion(db, model.id)
    if champion is None:
        raise ValueError(f"{model.name} has no current production version to roll back from")

    previous = (
        db.query(m.ModelVersion)
        .filter(m.ModelVersion.model_id == model.id, m.ModelVersion.stage == "archived", m.ModelVersion.id != champion.id)
        .order_by(m.ModelVersion.version.desc())
        .first()
    )
    if previous is None:
        raise ValueError(f"{model.name} has no previous archived version available to roll back to")

    now = datetime.utcnow()
    champion.is_champion = False
    champion.stage = "rolled_back"
    previous.is_champion = True
    previous.stage = "production"
    previous.promoted_at = now

    db.add(m.DeploymentEvent(model_version_id=champion.id, stage="rolled_back", status="SUCCESS",
                              detail=reason, created_at=now))
    db.add(m.DeploymentEvent(model_version_id=previous.id, stage="production", status="SUCCESS",
                              detail=f"restored via rollback of v{champion.version}", created_at=now + timedelta(seconds=1)))

    event = m.RollbackEvent(model_id=model.id, from_version_id=champion.id, to_version_id=previous.id,
                             reason=reason, triggered_by=triggered_by)
    db.add(event)

    _alert(db, run_id=None, model_version_id=champion.id, category="automatic_rollback", severity="CRITICAL",
           channel="pagerduty", message=f"{model.name}: rolled back from v{champion.version} to v{previous.version} — {reason}")
    _audit(db, action="rollback", resource_type="model_version", resource_id=champion.id,
           detail=f"{triggered_by} rollback: v{champion.version} -> v{previous.version} ({reason})")

    if champion.registry_version:
        mlflow_utils.transition_stage(model.name, champion.registry_version, "Archived")
    if previous.registry_version:
        mlflow_utils.transition_stage(model.name, previous.registry_version, "Production")

    db.commit()
    db.refresh(event)
    return event

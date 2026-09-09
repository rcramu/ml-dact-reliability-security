"""Startup bootstrap — seeds the customer-churn model + runs a representative
set of pipeline + monitoring runs so `docker compose up` alone produces a
fully explorable, story-complete stack (healthy promotion, blocked volume
anomaly, drift-triggered promotion, quality-warning rejection, regression
rejection, one rollback, and a monitoring history spanning stable/drifted/
severe_drift production traffic — including one AUTOMATIC drift-triggered
retrain)."""
import logging

from sqlalchemy.orm import Session

from . import models as m
from . import monitoring_engine as mon
from . import pipeline_engine as pe
from .database import Base, SessionLocal, engine

logger = logging.getLogger("churnplatform.seed")

MODEL_SPEC = {
    "name": "customer-churn", "task_type": "classification", "owner": "retention-ml",
    "description": "Predicts subscription churn risk for the Production ML Continuous Training Platform.",
}

# (trigger_type, trigger_detail, scenario)
RUN_PLAN = [
    ("schedule", "Weekly scheduled retraining (cron 0 2 * * 0)", "healthy"),
    ("data_availability", "New batch of ingested customer records (simulated volume anomaly)", "volume_anomaly"),
    ("drift", "Feature drift detected by the Drift Detection pipeline: PSI=0.24 on support_tickets_90d", "feature_drift"),
    ("schedule", "Weekly scheduled retraining (cron 0 2 * * 0)", "label_imbalance"),
    ("performance", "Production F1 dipped — investigating with a larger labeled sample", "regression"),
]

# (profile, auto_retrain) — walks the monitoring/decision-matrix story.
MONITORING_PLAN = [
    ("stable", False),
    ("drifted", False),
    ("severe_drift", True),  # this one should land HIGH drift + BAD/UNKNOWN evaluation -> auto retrain
]


def bootstrap() -> None:
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        if db.query(m.TrainedModel).count() > 0:
            logger.info("Database already seeded — skipping bootstrap")
            return

        pe.ensure_sla_config(db)

        model = m.TrainedModel(name=MODEL_SPEC["name"], task_type=MODEL_SPEC["task_type"],
                                owner_team=MODEL_SPEC["owner"], description=MODEL_SPEC["description"])
        db.add(model)
        db.flush()

        for trigger_type, trigger_detail, scenario in RUN_PLAN:
            pe.run_pipeline(db, model, trigger_type=trigger_type, trigger_detail=trigger_detail, scenario=scenario)

        # Demonstrate an automatic rollback: after the drift-triggered promotion (run 3)
        # becomes champion, simulate a production regression and roll back automatically.
        try:
            pe.rollback(db, model,
                        reason="Production regression detected: live accuracy dropped on the last 6h of traffic",
                        triggered_by="automatic")
        except ValueError as exc:
            logger.warning("Seed rollback skipped: %s", exc)

        # Re-run once more after the rollback with a fresh healthy dataset.
        pe.run_pipeline(db, model, trigger_type="manual",
                         trigger_detail="Re-run after rollback with a corrected dataset", scenario="healthy")

        # Walk the monitoring / decision-matrix story against the now-current champion.
        for profile, auto_retrain in MONITORING_PLAN:
            try:
                mon.run_monitoring_check(db, model, profile=profile, auto_retrain=auto_retrain)
            except ValueError as exc:
                logger.warning("Seed monitoring check (%s) skipped: %s", profile, exc)

        logger.info("Bootstrap complete: 1 model seeded (%s)", MODEL_SPEC["name"])
    finally:
        db.close()

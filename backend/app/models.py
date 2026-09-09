"""SQLAlchemy ORM models for the Production ML Continuous Training Platform
(req.md — training pipeline, registry, deployment, drift detection, alerts, audit)."""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TrainedModel(Base):
    """A model *name* that gets continuously retrained (req.md Sec. 1)."""
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_team: Mapped[str] = mapped_column(String(120), default="ml-platform")
    task_type: Mapped[str] = mapped_column(String(40), default="classification")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    versions: Mapped[list["ModelVersion"]] = relationship(back_populates="model", cascade="all, delete-orphan")
    dataset_versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="model", cascade="all, delete-orphan")
    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="model", cascade="all, delete-orphan")


class DatasetVersion(Base):
    """Versioned, seeded training dataset (req.md Sec. 1, 4, 12)."""
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("models.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    scenario: Mapped[str] = mapped_column(String(40), default="healthy")  # healthy/volume_anomaly/feature_drift/label_imbalance/regression
    source_type: Mapped[str] = mapped_column(String(20), default="synthetic")
    location: Mapped[str] = mapped_column(String(200), default="")  # S3 (MinIO) URI
    rows: Mapped[int] = mapped_column(Integer, default=0)
    features: Mapped[int] = mapped_column(Integer, default=8)
    train_split: Mapped[float] = mapped_column(Float, default=0.70)
    val_split: Mapped[float] = mapped_column(Float, default=0.15)
    test_split: Mapped[float] = mapped_column(Float, default=0.15)
    seed: Mapped[int] = mapped_column(Integer, default=42)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    model: Mapped["TrainedModel"] = relationship(back_populates="dataset_versions")
    records: Mapped[list["RawRecord"]] = relationship(back_populates="dataset_version", cascade="all, delete-orphan")
    quality_checks: Mapped[list["DataQualityCheck"]] = relationship(back_populates="dataset_version", cascade="all, delete-orphan")


class RawRecord(Base):
    """One synthetic ingested customer row (req.md Sec. 1, 4) — feeds PyTorch training."""
    __tablename__ = "raw_records"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    dataset_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("dataset_versions.id"), nullable=False)
    split: Mapped[str] = mapped_column(String(10), default="train")  # train/val/test
    tenure_months: Mapped[int] = mapped_column(Integer, default=0)
    monthly_charges: Mapped[float] = mapped_column(Float, default=0.0)
    age: Mapped[int] = mapped_column(Integer, default=0)
    support_tickets_90d: Mapped[int] = mapped_column(Integer, default=0)
    usage_hours_week: Mapped[float] = mapped_column(Float, default=0.0)
    is_month_to_month: Mapped[bool] = mapped_column(Boolean, default=False)
    autopay_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    has_addons: Mapped[bool] = mapped_column(Boolean, default=False)
    label: Mapped[int] = mapped_column(Integer, default=0)  # churn
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    dataset_version: Mapped["DatasetVersion"] = relationship(back_populates="records")


class DataQualityCheck(Base):
    """Pre-training data quality gate results — Great-Expectations-style checks (req.md Sec. 2, 4)."""
    __tablename__ = "data_quality_checks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    dataset_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("dataset_versions.id"), nullable=False)
    check_name: Mapped[str] = mapped_column(String(60), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=True)
    detail: Mapped[str] = mapped_column(Text, default="")

    dataset_version: Mapped["DatasetVersion"] = relationship(back_populates="quality_checks")


class ModelVersion(Base):
    """A trained candidate/production/archived/rejected model version (req.md Sec. 8-9)."""
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_model_version"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("models.id"), nullable=False)
    run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("pipeline_runs.id"), nullable=True)
    dataset_version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("dataset_versions.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), default="candidate")  # candidate/staging/production/archived/rejected/rolled_back
    framework: Mapped[str] = mapped_column(String(40), default="PyTorch")
    architecture: Mapped[str] = mapped_column(String(120), default="Feed-forward MLP (8-16-8-1)")
    hyperparams_json: Mapped[str] = mapped_column(Text, default="{}")
    mlflow_run_id: Mapped[str] = mapped_column(String(60), default="")
    registry_version: Mapped[int | None] = mapped_column(Integer, nullable=True)  # MLflow Model Registry's OWN version number
    git_commit: Mapped[str] = mapped_column(String(40), default="")
    decision_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    train_f1: Mapped[float] = mapped_column(Float, default=0.0)
    val_f1: Mapped[float] = mapped_column(Float, default=0.0)
    test_f1: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    precision: Mapped[float] = mapped_column(Float, default=0.0)
    recall: Mapped[float] = mapped_column(Float, default=0.0)
    roc_auc: Mapped[float] = mapped_column(Float, default=0.0)
    pr_auc: Mapped[float] = mapped_column(Float, default=0.0)
    is_champion: Mapped[bool] = mapped_column(Boolean, default=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    model: Mapped["TrainedModel"] = relationship(back_populates="versions")


class PipelineRun(Base):
    """One end-to-end training-DAG execution (req.md Sec. 5, 9)."""
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("models.id"), nullable=False)
    dataset_version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("dataset_versions.id"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")  # drift/performance/schedule/data_availability/volume_anomaly/manual
    trigger_detail: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING/SUCCESS/REJECTED/BLOCKED/FAILED
    outcome: Mapped[str] = mapped_column(String(40), default="")
    candidate_version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    model: Mapped["TrainedModel"] = relationship(back_populates="runs")
    stages: Mapped[list["PipelineStage"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class PipelineStage(Base):
    """One DAG stage (req.md Sec. 5)."""
    __tablename__ = "pipeline_stages"
    __table_args__ = (UniqueConstraint("run_id", "stage_name", name="uq_run_stage"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("pipeline_runs.id"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(60), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING/RUNNING/SUCCESS/FAILED/BLOCKED/SKIPPED
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    simulated_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["PipelineRun"] = relationship(back_populates="stages")


class SlaConfig(Base):
    __tablename__ = "sla_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    stage_name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    max_minutes: Mapped[float] = mapped_column(Float, default=10.0)


class SlaViolation(Base):
    __tablename__ = "sla_violations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("pipeline_runs.id"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(60), nullable=False)
    actual_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    max_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvaluationResult(Base):
    """Champion-vs-challenger quality-gate decision (req.md Sec. 9)."""
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("pipeline_runs.id"), nullable=False)
    candidate_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    champion_version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    candidate_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    champion_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    regression_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gate_result: Mapped[str] = mapped_column(String(10), default="PASS")  # PASS/FAIL
    reasons: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeploymentEvent(Base):
    """Canary rollout progression / rollback (req.md Sec. 10)."""
    __tablename__ = "deployment_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("model_versions.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)  # stage/smoke_test/canary_5/canary_25/canary_50/canary_100/production/rolled_back
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    detail: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RollbackEvent(Base):
    """Automatic/manual rollback record (req.md Sec. 19)."""
    __tablename__ = "rollback_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("models.id"), nullable=False)
    from_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    to_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), default="")
    triggered_by: Mapped[str] = mapped_column(String(20), default="automatic")  # automatic/manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductionPrediction(Base):
    """Every /predict call generates telemetry (req.md Sec. 11) — the reference dataset
    for drift detection and the source of Prometheus/Grafana operational metrics."""
    __tablename__ = "production_predictions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("model_versions.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(60), default=_uuid)
    tenure_months: Mapped[int] = mapped_column(Integer, default=0)
    monthly_charges: Mapped[float] = mapped_column(Float, default=0.0)
    age: Mapped[int] = mapped_column(Integer, default=0)
    support_tickets_90d: Mapped[int] = mapped_column(Integer, default=0)
    usage_hours_week: Mapped[float] = mapped_column(Float, default=0.0)
    is_month_to_month: Mapped[bool] = mapped_column(Boolean, default=False)
    autopay_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    has_addons: Mapped[bool] = mapped_column(Boolean, default=False)
    churn_probability: Mapped[float] = mapped_column(Float, default=0.0)
    prediction: Mapped[int] = mapped_column(Integer, default=0)
    ground_truth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    profile: Mapped[str] = mapped_column(String(20), default="stable")  # stable/drifted/severe_drift (simulation label)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DriftCheck(Base):
    """One monitoring-pipeline run: reference (training) vs production distribution (req.md Sec. 12-13)."""
    __tablename__ = "drift_checks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("models.id"), nullable=False)
    model_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("model_versions.id"), nullable=False)
    drift_level: Mapped[str] = mapped_column(String(10), default="LOW")  # LOW/HIGH
    evaluation_level: Mapped[str] = mapped_column(String(10), default="UNKNOWN")  # GOOD/BAD/UNKNOWN
    overall_status: Mapped[str] = mapped_column(String(12), default="NORMAL")  # GREEN/WARNING/CRITICAL/NORMAL
    recommended_action: Mapped[str] = mapped_column(String(60), default="Continue monitoring")
    max_psi: Mapped[float] = mapped_column(Float, default=0.0)
    production_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    triggered_retrain: Mapped[bool] = mapped_column(Boolean, default=False)
    retrain_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    feature_results: Mapped[list["DriftFeatureResult"]] = relationship(back_populates="drift_check", cascade="all, delete-orphan")


class DriftFeatureResult(Base):
    """Per-feature PSI/KS drift result belonging to a DriftCheck (req.md Sec. 12)."""
    __tablename__ = "drift_feature_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    drift_check_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("drift_checks.id"), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(60), nullable=False)
    psi: Mapped[float] = mapped_column(Float, default=0.0)
    ks_statistic: Mapped[float] = mapped_column(Float, default=0.0)
    ks_pvalue: Mapped[float] = mapped_column(Float, default=1.0)
    reference_mean: Mapped[float] = mapped_column(Float, default=0.0)
    production_mean: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(10), default="GREEN")  # GREEN/WARNING/CRITICAL

    drift_check: Mapped["DriftCheck"] = relationship(back_populates="feature_results")


class Alert(Base):
    """Slack/PagerDuty-style notification (req.md Sec. 9, 11-13)."""
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    model_version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    category: Mapped[str] = mapped_column(String(40), default="general")
    severity: Mapped[str] = mapped_column(String(12), default="INFO")  # INFO/WARNING/CRITICAL
    channel: Mapped[str] = mapped_column(String(20), default="slack")  # slack/pagerduty
    message: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Governance audit trail — every promote/reject/rollback/block decision (req.md Sec. 14)."""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), default="")
    resource_id: Mapped[str] = mapped_column(String(60), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

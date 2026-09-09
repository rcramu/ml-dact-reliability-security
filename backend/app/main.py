"""Production ML Continuous Training Platform backend — FastAPI app entrypoint."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import data_generator as gen
from . import models as m
from . import monitoring_engine as mon
from .config import settings
from .database import SessionLocal
from .integrations import s3_utils
from .integrations.otel_setup import configure_otel
from .integrations.prometheus_metrics import record_prediction
from .routers import (
    alerts, audit, data, health, monitoring, observability, pipeline, predict, registry, training,
)
from .seed import bootstrap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("churnplatform.main")

_live_task: asyncio.Task | None = None


async def _live_production_loop():
    """Keeps synthetic /predict-style traffic (and therefore Prometheus/Grafana) moving
    between manual demos — mirrors real production scoring traffic."""
    tick = 0
    while True:
        try:
            await asyncio.sleep(settings.production_tick_interval_seconds)
            tick += 1
            db = SessionLocal()
            try:
                model = db.query(m.TrainedModel).filter_by(name="customer-churn").one_or_none()
                if model is None:
                    continue
                champion = db.query(m.ModelVersion).filter_by(model_id=model.id, is_champion=True).one_or_none()
                if champion is None:
                    continue
                from . import predictor
                from .ml.pytorch_trainer import predict as torch_predict

                batch = gen.generate_production_batch("stable", gen.stable_seed(f"live:{tick}"), n=5)
                trained, threshold = predictor.get_or_train(db, champion)
                for row in batch:
                    x, _y = gen.production_records_to_arrays([row])
                    prob = float(torch_predict(trained, x)[0])
                    prediction = int(prob >= threshold)
                    db.add(m.ProductionPrediction(
                        model_version_id=champion.id, tenure_months=row["tenure_months"],
                        monthly_charges=row["monthly_charges"], age=row["age"],
                        support_tickets_90d=row["support_tickets_90d"], usage_hours_week=row["usage_hours_week"],
                        is_month_to_month=row["is_month_to_month"], autopay_enabled=row["autopay_enabled"],
                        has_addons=row["has_addons"], churn_probability=round(prob, 4), prediction=prediction,
                        ground_truth=row["ground_truth"], latency_ms=2.5, profile="stable",
                    ))
                    record_prediction(model.name, str(champion.version), probability=prob, latency_seconds=0.0025)
                db.commit()

                # Every ~6th tick, also run a lightweight drift check (stable profile by default).
                if tick % 6 == 0:
                    mon.run_monitoring_check(db, model, profile="stable", auto_retrain=True, seed=gen.stable_seed(f"live-drift:{tick}"))
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - background task must never crash the app
            logger.warning("Live production tick failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _live_task
    logger.info("Bootstrapping Production ML Continuous Training Platform: seeding model + pipeline history…")
    try:
        s3_utils.ensure_bucket()
    except Exception:
        logger.warning("MinIO not reachable yet at startup — will retry lazily on first upload", exc_info=True)
    bootstrap()
    _live_task = asyncio.create_task(_live_production_loop())
    logger.info("Bootstrap complete — API ready")
    yield
    if _live_task:
        _live_task.cancel()


app = FastAPI(
    title="Production ML Continuous Training Platform API",
    description=(
        "Airflow-orchestrated, PyTorch-trained, MLflow-tracked customer-churn model with a "
        "16-stage training DAG, Great-Expectations-style data validation, an automated quality "
        "gate, canary deployment + rollback, drift-vs-evaluation decision-matrix monitoring with "
        "automatic retraining, and full Prometheus/Grafana/Splunk observability — backed by "
        "PostgreSQL and MinIO (S3)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

configure_otel(app)

app.include_router(health.router)
app.include_router(data.router)
app.include_router(training.router)
app.include_router(registry.router)
app.include_router(pipeline.router)
app.include_router(monitoring.router)
app.include_router(predict.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(observability.router)

API_CATALOG = {
    "service": "Production ML Continuous Training Platform API",
    "version": "1.0.0",
    "description": "Every endpoint below is documented automatically via FastAPI's OpenAPI schema.",
    "swagger_url": "/docs",
    "redoc_url": "/redoc",
    "openapi_url": "/openapi.json",
    "groups": [
        {"tag": "Health", "description": "Liveness/readiness probes.", "endpoints": [
            {"method": "GET", "path": "/health", "description": "Liveness probe"},
            {"method": "GET", "path": "/ready", "description": "Readiness — DB + seeding status"},
        ]},
        {"tag": "Ingested Data", "description": "Browse every raw/derived table — the actual ingested customer data.", "endpoints": [
            {"method": "GET", "path": "/data/summary", "description": "Ingestion counts across every table"},
            {"method": "GET", "path": "/data/datasets", "description": "Browse seeded dataset versions"},
            {"method": "GET", "path": "/data/records", "description": "Browse ingested raw customer records"},
            {"method": "GET", "path": "/data/data-quality-checks", "description": "Browse data-quality gate results"},
            {"method": "GET", "path": "/data/predictions", "description": "Browse recent /predict calls"},
            {"method": "GET", "path": "/data/s3-objects", "description": "Browse objects in the MinIO (S3) bucket"},
            {"method": "GET", "path": "/data/audit-log", "description": "Governance / audit trail"},
            {"method": "GET", "path": "/data/seed-scenarios", "description": "List the 5 seedable data scenarios"},
        ]},
        {"tag": "Training", "description": "Trigger and inspect the 16-stage training DAG.", "endpoints": [
            {"method": "POST", "path": "/api/v1/models/{model}/training", "description": "Trigger a full training run"},
            {"method": "GET", "path": "/api/v1/models/{model}/training/{run_id}", "description": "Training run status + every stage"},
            {"method": "GET", "path": "/api/v1/models/{model}/training/history", "description": "Training run history"},
            {"method": "GET", "path": "/api/v1/models/{model}/evaluation/{run_id}", "description": "Quality-gate evaluation result"},
            {"method": "POST", "path": "/api/v1/models/{model}/rollback", "description": "Roll back to the previous production version"},
        ]},
        {"tag": "Models & Registry", "description": "Champion/challenger + version lineage.", "endpoints": [
            {"method": "GET", "path": "/api/v1/models", "description": "List every model + its current champion"},
            {"method": "GET", "path": "/api/v1/models/{model}/versions", "description": "All versions for a model"},
            {"method": "GET", "path": "/api/v1/models/{model}/deployment", "description": "Deployment/canary + rollback timeline"},
        ]},
        {"tag": "Drift & Monitoring", "description": "Reference-vs-production drift detection + decision matrix.", "endpoints": [
            {"method": "POST", "path": "/api/v1/models/{model}/monitoring/check", "description": "Run a drift + evaluation check"},
            {"method": "GET", "path": "/api/v1/models/{model}/monitoring/history", "description": "Drift check history"},
            {"method": "GET", "path": "/api/v1/models/{model}/monitoring/{check_id}", "description": "Drift check detail — per-feature PSI/KS"},
            {"method": "GET", "path": "/api/v1/models/{model}/monitoring/decision-matrix", "description": "The 6-outcome decision matrix"},
        ]},
        {"tag": "Prediction", "description": "Real-time inference against the production champion.", "endpoints": [
            {"method": "POST", "path": "/api/v1/models/{model}/predict", "description": "Score a customer for churn risk"},
            {"method": "GET", "path": "/api/v1/models/{model}/predict/history", "description": "Browse recent live predictions"},
        ]},
        {"tag": "Pipeline Runs", "description": "Cross-model DAG run visibility + SLA dashboard.", "endpoints": [
            {"method": "GET", "path": "/pipeline/runs", "description": "List pipeline runs across every model"},
            {"method": "GET", "path": "/pipeline/runs/{run_id}", "description": "Pipeline run detail — every DAG stage"},
            {"method": "GET", "path": "/pipeline/sla", "description": "SLA thresholds + violations"},
        ]},
        {"tag": "Alerts", "description": "Slack/PagerDuty-style notifications.", "endpoints": [
            {"method": "GET", "path": "/alerts", "description": "List alerts"},
            {"method": "POST", "path": "/alerts/{alert_id}/resolve", "description": "Resolve an alert"},
        ]},
        {"tag": "Governance & Audit", "description": "Every promote/reject/rollback/block decision, who/what/when/why.", "endpoints": [
            {"method": "GET", "path": "/audit", "description": "List audit log entries"},
        ]},
        {"tag": "Observability", "description": "Prometheus scrape + seedable traffic profiles.", "endpoints": [
            {"method": "GET", "path": "/metrics", "description": "Prometheus scrape endpoint"},
            {"method": "GET", "path": "/observability/seed-profiles", "description": "List seedable production-traffic profiles"},
        ]},
    ],
}


@app.get("/docs-catalog", tags=["Meta"], summary="Machine-readable API reference (powers the UI's API Reference tab)")
def docs_catalog():
    return API_CATALOG

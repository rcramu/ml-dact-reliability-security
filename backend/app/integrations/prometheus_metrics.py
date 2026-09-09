"""Prometheus metrics (req.md Sec. 11) — scraped by the prometheus container."""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

PREDICTIONS_TOTAL = Counter(
    "churn_prediction_requests_total", "Total /predict calls served",
    ["model", "model_version", "status"],
)
PREDICTION_ERRORS_TOTAL = Counter(
    "churn_prediction_errors_total", "Total /predict errors",
    ["model", "model_version"],
)
LATENCY_SECONDS = Histogram(
    "churn_prediction_latency_seconds", "Inference latency in seconds",
    ["model", "model_version"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0),
)
MODEL_CONFIDENCE = Gauge(
    "churn_model_confidence_avg", "Rolling average churn_probability of recent predictions",
    ["model", "model_version"],
)
DRIFT_PSI = Gauge(
    "churn_drift_psi_max", "Latest monitoring run's max feature PSI",
    ["model"],
)
TRAINING_RUNS_TOTAL = Counter(
    "churn_training_runs_total", "Total training pipeline runs",
    ["model", "status"],
)


def record_prediction(model_name: str, version: str, *, probability: float, latency_seconds: float, error: bool = False):
    status = "error" if error else "ok"
    PREDICTIONS_TOTAL.labels(model_name, version, status).inc()
    if error:
        PREDICTION_ERRORS_TOTAL.labels(model_name, version).inc()
        return
    LATENCY_SECONDS.labels(model_name, version).observe(latency_seconds)
    MODEL_CONFIDENCE.labels(model_name, version).set(probability)


def record_drift(model_name: str, max_psi: float):
    DRIFT_PSI.labels(model_name).set(max_psi)


def record_training_run(model_name: str, status: str):
    TRAINING_RUNS_TOTAL.labels(model_name, status).inc()


def latest_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

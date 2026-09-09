"""Monitoring pipeline DAG (req.md Sec. 11-13) — the feedback loop.

Production predictions -> Drift Detection -> Drift > threshold? -> Airflow
Trigger -> Training DAG -> New model -> Evaluation -> Deployment

This DAG periodically asks the backend to compare production traffic against
the training distribution; when drift is HIGH and the model's evaluated
quality is not confirmed GOOD, the backend automatically triggers a new
training run itself (see backend/app/monitoring_engine.py) — this DAG's job
is purely to schedule that check and alert on the outcome.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

BACKEND_URL = "http://backend:8000"
MODEL_NAME = "customer-churn"

default_args = {
    "owner": "ml-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}


def _check_drift(**_context) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/models/{MODEL_NAME}/monitoring/check",
        json={"profile": "stable", "auto_retrain": True},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    logger.info("Drift check %s -> drift=%s evaluation=%s overall=%s retrain_triggered=%s",
                payload["id"], payload["drift_level"], payload["evaluation_level"],
                payload["overall_status"], payload["triggered_retrain"])
    return payload


def _alert_if_required(**context) -> None:
    payload = context["ti"].xcom_pull(task_ids="check_drift")
    if payload["overall_status"] in ("WARNING", "CRITICAL"):
        logger.warning("ALERT: monitoring check %s -> %s (%s)", payload["id"], payload["overall_status"], payload["recommended_action"])
    if payload["triggered_retrain"]:
        logger.warning("Drift-triggered retraining started automatically: run %s", payload["retrain_run_id"])


with DAG(
    dag_id="monitoring_pipeline",
    description="req.md Sec. 11-13 — drift detection against production traffic, with automatic retraining",
    default_args=default_args,
    schedule="*/30 * * * *",  # every 30 minutes
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["continuous-training", "drift-detection"],
) as dag:

    check_drift = PythonOperator(
        task_id="check_drift",
        python_callable=_check_drift,
    )

    alert_if_required = PythonOperator(
        task_id="alert_if_required",
        python_callable=_alert_if_required,
    )

    check_drift >> alert_if_required

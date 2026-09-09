"""Training pipeline DAG (req.md Sec. 5, DAG 2) — the most important DAG.

check_new_dataset -> validate_data -> feature_engineering -> split_dataset ->
train_pytorch -> evaluate_model -> quality_gate -> [alert | register_model]

Airflow triggers the backend's 16-stage training pipeline on a schedule and
inspects the outcome — the actual DAG execution (every stage below) happens
inside POST /api/v1/models/{model}/training, matching this repo's "Airflow
orchestrates, backend does the real work" convention (see backend/app/
pipeline_engine.py for the full stage-by-stage implementation).
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
    "retry_delay": timedelta(minutes=5),
}


def _trigger_training_pipeline(**_context) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/models/{MODEL_NAME}/training",
        json={"trigger_type": "schedule", "scenario": "healthy", "trigger_detail": "Weekly scheduled retraining (Airflow)"},
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    logger.info("Training run %s -> status=%s outcome=%s", payload["id"], payload["status"], payload.get("outcome"))
    return payload


def _alert_if_rejected(**context) -> None:
    payload = context["ti"].xcom_pull(task_ids="trigger_training_pipeline")
    if payload["status"] in ("REJECTED", "BLOCKED", "FAILED"):
        logger.warning("ALERT: training run %s ended %s (%s) — see /alerts in the platform UI",
                        payload["id"], payload["status"], payload.get("outcome"))
    else:
        logger.info("Training run %s completed successfully (%s)", payload["id"], payload.get("outcome"))


with DAG(
    dag_id="training_pipeline",
    description="req.md Sec. 5 — check_new_dataset -> validate_data -> feature_engineering -> "
                "split_dataset -> train_pytorch -> evaluate_model -> quality_gate -> register_model",
    default_args=default_args,
    schedule="0 2 * * 0",  # weekly, Sunday 2 AM
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["continuous-training", "pytorch", "mlflow"],
) as dag:

    trigger_training_pipeline = PythonOperator(
        task_id="trigger_training_pipeline",
        python_callable=_trigger_training_pipeline,
    )

    alert_if_rejected = PythonOperator(
        task_id="alert_if_rejected",
        python_callable=_alert_if_rejected,
    )

    trigger_training_pipeline >> alert_if_rejected

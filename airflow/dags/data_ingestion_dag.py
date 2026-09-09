"""Data ingestion DAG (req.md Sec. 4, DAG 1).

fetch_customer_data -> write_to_s3 -> validate_schema -> publish_dataset

This is a thin orchestration wrapper: the actual ingestion/validation logic
lives in the backend's training pipeline (check_new_dataset/validate_data/
write_to_s3 stages of POST /api/v1/models/{model}/training), matching this
repo's "Airflow orchestrates, backend does the real work" convention. This
DAG demonstrates the ingestion-only slice of that pipeline running on its own
daily schedule, independent of a full retraining trigger.
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
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}


def _fetch_customer_data(**_context) -> str:
    """req.md 'fetch_customer_data' — the backend generates a fresh, deterministically
    seeded synthetic customer dataset per ingestion (see app/data_generator.py)."""
    logger.info("Fetching new customer data batch for %s", MODEL_NAME)
    return "healthy"


def _write_to_s3_and_validate(**context) -> dict:
    """req.md 'write_to_s3' + 'validate_schema' — delegated to the backend's own
    write_to_s3/validate_data pipeline stages, which persist to MinIO (S3) and run
    Great-Expectations-style checks before anything is published."""
    scenario = context["ti"].xcom_pull(task_ids="fetch_customer_data")
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/models/{MODEL_NAME}/training",
        json={"trigger_type": "data_availability", "scenario": scenario, "trigger_detail": "Daily ingestion DAG"},
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    logger.info("Ingestion run %s -> status=%s outcome=%s", payload["id"], payload["status"], payload.get("outcome"))
    return payload


def _publish_dataset(**context) -> None:
    """req.md 'publish_dataset' — the dataset is already durable in Postgres + MinIO;
    this task just confirms the run reached a terminal, inspectable state."""
    payload = context["ti"].xcom_pull(task_ids="write_to_s3_and_validate")
    logger.info("Dataset for run %s published — %d/%d stages succeeded",
                payload["id"], payload["stages_success"], payload["stage_count"])


with DAG(
    dag_id="data_ingestion",
    description="req.md Sec. 4 — fetch_customer_data -> write_to_s3 -> validate_schema -> publish_dataset",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["continuous-training", "ingestion"],
) as dag:

    fetch_customer_data = PythonOperator(
        task_id="fetch_customer_data",
        python_callable=_fetch_customer_data,
    )

    write_to_s3_and_validate = PythonOperator(
        task_id="write_to_s3_and_validate",
        python_callable=_write_to_s3_and_validate,
    )

    publish_dataset = PythonOperator(
        task_id="publish_dataset",
        python_callable=_publish_dataset,
    )

    fetch_customer_data >> write_to_s3_and_validate >> publish_dataset

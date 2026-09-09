"""Central configuration for the Production ML Continuous Training Platform
(req.md — Customer Churn Prediction)."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://cmp_user:cmp_pass@postgres:5432/churn_platform"
    random_seed: int = 42

    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment: str = "customer-churn"

    # S3-compatible object storage (MinIO stands in for Amazon S3, req.md Sec. 2/4)
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "cmp_minio"
    s3_secret_key: str = "cmp_minio_secret"
    s3_bucket: str = "churn-platform"
    s3_region: str = "us-east-1"

    # Splunk HEC (req.md Sec. 17)
    splunk_hec_url: str = "https://splunk:8088/services/collector"
    splunk_hec_token: str = "00000000-0000-0000-0000-000000000000"
    splunk_verify_tls: bool = False
    splunk_index: str = "churn_platform"

    # OpenTelemetry (req.md Sec. 17)
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"
    otel_service_name: str = "churn-platform-backend"

    # synthetic churn dataset (req.md Sec. 1, 4)
    baseline_rows: int = 1200
    expected_volume: int = 1200
    volume_anomaly_tolerance: float = 0.20

    # PyTorch trainer (req.md Sec. 6-7)
    train_epochs: int = 120
    train_batch_size: int = 32
    train_learning_rate: float = 0.01
    hidden_dim_1: int = 16
    hidden_dim_2: int = 8

    # Evaluation / regression gate (req.md Sec. 9)
    minimum_f1: float = 0.65
    minimum_recall: float = 0.55
    minimum_precision: float = 0.55
    max_regression_pct: float = 10.0

    # Drift detection thresholds (req.md Sec. 12) — PSI classification bands
    psi_warning: float = 0.10
    psi_critical: float = 0.25

    # Continuous-training feedback loop (req.md Sec. 13)
    drift_check_interval_seconds: int = 25
    production_tick_interval_seconds: int = 8

    class Config:
        env_prefix = "CMP_"


settings = Settings()

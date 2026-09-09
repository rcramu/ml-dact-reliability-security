import { useState } from 'react'
import { useConceptInterval } from '../hooks/useConceptInterval.js'

const REPO_LAYOUT = [
  { path: 'backend/app/config.py', role: 'Pydantic settings — DB/MLflow/S3/Splunk/OTel URLs, dataset sizing, PyTorch hyperparameters, gate thresholds, drift thresholds' },
  { path: 'backend/app/models.py', role: 'SQLAlchemy ORM — models, dataset_versions, raw_records, model_versions, pipeline_runs/stages, evaluation_results, deployment_events, drift_checks, alerts, audit_logs' },
  { path: 'backend/app/data_generator.py', role: 'Deterministic synthetic churn-customer generator for every seeded scenario + live production traffic' },
  { path: 'backend/app/pipeline_engine.py', role: 'The 16-stage training DAG engine — check_new_dataset through publish_metrics, plus rollback()' },
  { path: 'backend/app/monitoring_engine.py', role: 'The drift-detection feedback loop — PSI/KS vs. reference distribution, decision matrix, automatic retraining' },
  { path: 'backend/app/predictor.py', role: 'In-memory champion model cache — retrains from persisted data on a cache miss (e.g. after a restart)' },
  { path: 'backend/app/seed.py', role: 'Startup bootstrap: seed the model -> run 6 training scenarios -> rollback demo -> 3 monitoring checks' },
  { path: 'backend/app/ml/pytorch_trainer.py', role: 'ChurnMLP (8-16-8-1) + BCEWithLogitsLoss training loop + threshold tuning' },
  { path: 'backend/app/ml/gates.py', role: 'The quality gate — absolute floors + max-regression-vs-champion check' },
  { path: 'backend/app/ml/drift.py', role: 'PSI + Kolmogorov-Smirnov implementations (from scratch, numpy/scipy)' },
  { path: 'backend/app/ml/decision_matrix.py', role: 'The 6-outcome drift x evaluation lookup table + should_retrain()' },
  { path: 'backend/app/ml/data_quality.py', role: 'Great-Expectations-style checks (schema, nulls, labels, class balance, freshness)' },
  { path: 'backend/app/integrations/mlflow_utils.py', role: 'MLflow run logging + Model Registry registration/stage transitions' },
  { path: 'backend/app/integrations/s3_utils.py', role: 'MinIO/S3 bucket + object read/write' },
  { path: 'backend/app/integrations/splunk_utils.py', role: 'Splunk HEC event delivery' },
  { path: 'backend/app/integrations/prometheus_metrics.py', role: 'Prometheus counters/histograms/gauges for predictions, drift, and training runs' },
  { path: 'backend/app/routers/', role: 'health, data, training, registry, pipeline, monitoring, predict, alerts, audit, observability' },
  { path: 'airflow/dags/', role: 'data_ingestion_dag.py, training_pipeline_dag.py, monitoring_pipeline_dag.py — thin wrappers calling the backend API' },
  { path: 'observability/', role: 'Prometheus scrape config, Grafana provisioning + dashboard JSON, OTel collector config' },
  { path: 'frontend/', role: 'React console — Ingested Data, Pipeline Runs, Model Registry, Drift & Monitoring, Predict, Alerts, API Reference, Knowledge Base' },
]

const FLOWS = [
  {
    name: 'Startup bootstrap',
    steps: [
      'FastAPI lifespan handler ensures the MinIO bucket exists, then calls seed.bootstrap()',
      'On a fresh DB: seeds the customer-churn model and runs 6 training scenarios (healthy, volume_anomaly, feature_drift, label_imbalance, regression, then a manual re-run)',
      'Attempts an automatic rollback demonstration, then walks 3 monitoring checks (stable, drifted, severe_drift)',
      'Starts the asyncio live-production background task, which generates ongoing /predict-style traffic and periodic drift checks',
      'Reports ready via GET /ready once the model + at least one version exist',
    ],
  },
  {
    name: 'POST /api/v1/models/{model}/training (manual or Airflow)',
    steps: [
      'check_new_dataset generates a fresh, seeded batch of customer records for the requested scenario',
      'validate_data runs 5 Great-Expectations-style checks; check_volume_anomaly can BLOCK the run entirely',
      'write_to_s3 persists the dataset to MinIO; feature_engineering + split_dataset prepare train/val/test arrays',
      'train_pytorch trains a fresh ChurnMLP; log_mlflow records params/metrics to its own MLflow run',
      'evaluate_model tunes the decision threshold on validation, then quality_gate compares the candidate to the current champion',
      'On PASS: register_model, then a canary deploy_stage/smoke_test/deploy_production sequence promotes the new champion',
    ],
  },
  {
    name: 'POST /api/v1/models/{model}/monitoring/check (manual or Airflow)',
    steps: [
      'Loads the champion\'s original training records as the reference distribution',
      'Generates a simulated batch of production traffic for the requested profile (stable/drifted/severe_drift)',
      'Computes PSI + KS per feature, and production accuracy vs. the champion\'s own recorded accuracy',
      'Combines drift_level and evaluation_level via the decision matrix into an overall_status',
      'If drift is HIGH and evaluation is not confirmed GOOD, automatically calls run_pipeline(trigger_type="drift") itself',
    ],
  },
]

function FlowSteps({ title, steps }) {
  const [active, setActive] = useState(0)
  useConceptInterval(() => setActive((p) => (p + 1) % steps.length), 2800, [steps.length])
  const current = steps[active]

  return (
    <div className="concept-diagram code-flow">
      <div className="concept-diagram-head">
        <span className="concept-label">{title}</span>
        <span className="concept-step-counter">Step {active + 1}/{steps.length}</span>
      </div>
      <ol className="code-flow-list">
        {steps.map((step, index) => (
          <li key={step} className={`code-flow-step ${index === active ? 'active' : ''}`}>
            <span className="code-flow-num">{index + 1}</span>
            <p>{step}</p>
          </li>
        ))}
      </ol>
      {current && (
        <div className="concept-callout">
          <strong>Step {active + 1}</strong>
          <p>{current}</p>
        </div>
      )}
    </div>
  )
}

export default function CodeTab() {
  return (
    <div className="grid">
      <section className="card span-2">
        <h2>Explain the code</h2>
        <p className="muted">Repo layout and the three key request/DAG flows behind this app's dashboards.</p>
      </section>

      <section className="card span-2">
        <h3>Repository layout</h3>
        <ul className="repo-tree">
          {REPO_LAYOUT.map((r) => (
            <li key={r.path}><code>{r.path}</code><span>{r.role}</span></li>
          ))}
        </ul>
      </section>

      {FLOWS.map((flow) => (
        <section key={flow.name} className="card span-2">
          <h3>{flow.name}</h3>
          <FlowSteps title={flow.name} steps={flow.steps} />
        </section>
      ))}
    </div>
  )
}

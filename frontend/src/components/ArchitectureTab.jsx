import FlowAnimation from './diagrams/FlowAnimation.jsx'

const TRAINING_STEPS = [
  { id: 'airflow', label: 'Airflow trigger', color: '#94a3b8' },
  { id: 'ingest', label: 'Ingest + validate', color: '#0ea5e9' },
  { id: 'train', label: 'PyTorch train', color: '#6366f1' },
  { id: 'gate', label: 'Quality gate', color: '#f59e0b' },
  { id: 'deploy', label: 'Canary deploy', color: '#059669' },
]

const MONITORING_STEPS = [
  { id: 'predict', label: '/predict traffic', color: '#94a3b8' },
  { id: 'psi', label: 'PSI + KS vs training', color: '#0ea5e9' },
  { id: 'matrix', label: 'Decision matrix', color: '#7c3aed' },
  { id: 'retrain', label: 'Auto-retrain?', color: '#f59e0b' },
  { id: 'alert', label: 'Alert / Splunk', color: '#f87171' },
]

const COMPONENTS = [
  { name: 'PostgreSQL 16', role: 'models, dataset_versions, raw_records, model_versions, pipeline_runs/stages, evaluation_results, deployment_events, drift_checks, alerts, audit_logs' },
  { name: 'FastAPI backend', role: 'REST API, request validation (Pydantic), Swagger/OpenAPI docs, live production-traffic simulation background task' },
  { name: 'MLflow server', role: 'Its own container — tracks every training run and owns the Model Registry (Staging/Production/Archived)' },
  { name: 'PyTorch ChurnMLP', role: 'Feed-forward MLP (8-16-8-1), trained fresh per pipeline run on the seeded synthetic churn dataset' },
  { name: 'scikit-learn', role: 'Classification metrics (accuracy/precision/recall/F1/ROC-AUC/PR-AUC) for the quality gate' },
  { name: 'SciPy', role: 'Kolmogorov-Smirnov test for drift detection' },
  { name: 'Prometheus + Grafana', role: 'Real metrics scraping + dashboards — churn_prediction_*/churn_drift_psi_max/churn_training_runs_total' },
  { name: 'Splunk (HEC)', role: 'Structured event delivery for pipeline alerts, predictions, and drift checks' },
  { name: 'OpenTelemetry + otel-collector', role: 'Distributed tracing of every API request, exported to the collector container' },
  { name: 'MinIO (S3-compatible)', role: 'Stores every ingested dataset version as a real S3 object (stands in for Amazon S3)' },
  { name: 'Apache Airflow', role: 'Real webserver + scheduler orchestrating 3 DAGs: data_ingestion, training_pipeline, monitoring_pipeline' },
  { name: 'React + Vite UI', role: 'Ingested Data, Pipeline Runs, Model Registry, Drift & Monitoring, Predict, Alerts, API Reference, Knowledge Base' },
]

const NFRS = [
  { name: 'Reproducibility', target: 'Fixed, sha256-derived seed for every scenario generator', measure: 'Same seed -> same ingested data, same trained weights, same evaluation metrics' },
  { name: 'Resilience', target: 'Monitoring/observability failure must never affect training or serving', measure: 'Splunk/OTel/MinIO calls are all try/except-wrapped and non-blocking' },
  { name: 'Safety', target: 'Never promote a regressing model', measure: 'quality_gate combines absolute floors AND a max-regression-vs-champion check' },
  { name: 'Auditability', target: 'Every promote/reject/rollback/block decision traceable', measure: 'AuditLog row + MLflow run id + Alert on every pipeline outcome' },
]

const ROADMAP_PHASES = [
  { phase: 'Phase 1 (this app)', detail: 'Local Airflow + PostgreSQL + sample dataset' },
  { phase: 'Phase 2 (this app)', detail: 'MinIO (S3) + PyTorch training' },
  { phase: 'Phase 3 (this app)', detail: 'MLflow tracking + Model Registry' },
  { phase: 'Phase 4 (simulated)', detail: 'Airflow -> KubernetesPodOperator -> EKS (canary stages recorded, no real cluster)' },
  { phase: 'Phase 5 (this app)', detail: 'FastAPI model serving (POST /predict)' },
  { phase: 'Phase 6 (this app)', detail: 'Prometheus + Grafana + Splunk' },
  { phase: 'Phase 7 (this app)', detail: 'Drift detection (PSI/KS)' },
  { phase: 'Phase 8 (this app)', detail: 'Automated, decision-matrix-gated retraining' },
  { phase: 'Phase 9 (roadmap)', detail: 'CI/CD (GitHub Actions) + Terraform + security scanning (Trivy/Bandit)' },
  { phase: 'Phase 10 (roadmap)', detail: 'Failure-injection testing, formal SLOs, IAM/IRSA/KMS/Secrets Manager, production hardening' },
]

export default function ArchitectureTab() {
  return (
    <div className="grid">
      <section className="card span-2">
        <h2>Training pipeline architecture</h2>
        <p>Airflow triggers the backend's own 16-stage pipeline; the backend does all the real work (data, training, gating, deployment) and reports back — the same "orchestrate, don't reimplement" pattern used throughout this platform.</p>
        <FlowAnimation steps={TRAINING_STEPS} caption="Airflow trigger -> ingest &amp; validate -> PyTorch train -> quality gate -> canary deploy" />
      </section>

      <section className="card span-2">
        <h2>Monitoring / feedback-loop architecture</h2>
        <FlowAnimation steps={MONITORING_STEPS} caption="Production traffic -> PSI/KS vs. training distribution -> decision matrix -> automatic retrain -> alert" />
      </section>

      <section className="card">
        <h2>Components</h2>
        <ul className="arch-list">
          {COMPONENTS.map((c) => (
            <li key={c.name}><strong>{c.name}</strong> — {c.role}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Non-functional requirements</h2>
        <table className="data-table">
          <thead><tr><th>NFR</th><th>Target</th><th>Measure</th></tr></thead>
          <tbody>
            {NFRS.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td>{row.target}</td>
                <td className="muted">{row.measure}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card span-2">
        <h2>Full production roadmap (req.md's recommended implementation order)</h2>
        <ol className="about-steps">
          {ROADMAP_PHASES.map((p) => (
            <li key={p.phase}><strong>{p.phase}:</strong> {p.detail}</li>
          ))}
        </ol>
      </section>
    </div>
  )
}

import FlowAnimation from './diagrams/FlowAnimation.jsx'

const STACK_STEPS = [
  { id: 'react', label: 'React + Vite', color: '#6366f1' },
  { id: 'nginx', label: 'nginx', color: '#94a3b8' },
  { id: 'fastapi', label: 'FastAPI', color: '#059669' },
  { id: 'airflow', label: 'Airflow', color: '#017cee' },
  { id: 'torch', label: 'PyTorch', color: '#ee4c2c' },
  { id: 'mlflow', label: 'MLflow', color: '#0ea5e9' },
  { id: 'prom', label: 'Prometheus', color: '#f59e0b' },
  { id: 'grafana', label: 'Grafana', color: '#f97316' },
]

const CATEGORIES = [
  {
    name: 'Orchestration',
    tools: [
      { name: 'Apache Airflow', role: 'Workflow orchestration', why: 'Three real DAGs (data_ingestion, training_pipeline, monitoring_pipeline) with LocalExecutor, a webserver, and a scheduler — exactly the tool req.md names for orchestration.' },
    ],
  },
  {
    name: 'Backend',
    tools: [
      { name: 'FastAPI', role: 'REST API framework', why: 'Auto-generates Swagger/OpenAPI docs directly from Pydantic type hints — matches req.md\'s "document all APIs" requirement for free.' },
      { name: 'Pydantic', role: 'Request/response validation', why: 'Every schema in schemas.py becomes both runtime validation and Swagger documentation.' },
      { name: 'SQLAlchemy', role: 'ORM', why: 'Declarative models map directly onto req.md\'s recommended data model (models, versions, runs, drift checks, alerts).' },
      { name: 'asyncio', role: 'Live production traffic simulation', why: 'A background task keeps generating fresh /predict-style traffic and periodic drift checks between manual demos.' },
    ],
  },
  {
    name: 'ML / Data',
    tools: [
      { name: 'PyTorch', role: 'Churn classifier', why: 'req.md\'s explicit ML framework — a small feed-forward MLP (ChurnMLP) trained from scratch on every pipeline run.' },
      { name: 'scikit-learn', role: 'Classification metrics', why: 'Precision/recall/F1/ROC-AUC/PR-AUC for the quality gate.' },
      { name: 'SciPy', role: 'Kolmogorov-Smirnov test', why: 'Statistical corroboration alongside PSI for drift detection.' },
      { name: 'MLflow', role: 'Experiment tracking + Model Registry', why: 'Its own container — every training run and every promotion is tracked and versioned.' },
      { name: 'NumPy', role: 'Synthetic data generation', why: 'Deterministic seeded random generators for every scenario in the training and monitoring pipelines.' },
      { name: 'Great Expectations (stand-in)', role: 'Data validation', why: 'req.md names Great Expectations explicitly; this build implements the same 5 checks from scratch (app/ml/data_quality.py) to keep the image lean.' },
    ],
  },
  {
    name: 'Observability',
    tools: [
      { name: 'Prometheus', role: 'Metrics collection', why: 'Scrapes real churn_prediction_*/churn_drift_psi_max/churn_training_runs_total metrics from the backend every 15s.' },
      { name: 'Grafana', role: 'Dashboards', why: 'Auto-provisioned Prometheus + PostgreSQL datasources and a Churn Platform dashboard.' },
      { name: 'Splunk (HEC)', role: 'Enterprise event delivery', why: 'Structured JSON events for pipeline alerts, predictions, and drift checks.' },
      { name: 'OpenTelemetry', role: 'Distributed tracing', why: 'Auto-instruments every FastAPI request, exporting spans to the otel-collector container.' },
    ],
  },
  {
    name: 'Platform',
    tools: [
      { name: 'PostgreSQL 16', role: 'System of record', why: 'Every ingested/derived table: customers, dataset versions, model versions, pipeline runs, drift checks, alerts, audit logs.' },
      { name: 'MinIO', role: 'S3-compatible object storage', why: 'Real S3 API calls via boto3 for every dataset version, entirely offline (stands in for req.md\'s Amazon S3).' },
      { name: 'Docker Compose', role: 'Orchestration', why: 'One command starts all 12 services together, standing in for req.md\'s AWS EKS deployment target.' },
      { name: 'React + Vite', role: 'Frontend framework', why: 'Fast dev server, small production bundle via nginx.' },
    ],
  },
]

export default function ToolsFrameworksTab() {
  return (
    <div className="grid tools-frameworks">
      <section className="card span-2">
        <h2>Tools &amp; frameworks used in this project</h2>
        <p>Every tool below is actually running in this docker-compose stack — nothing here is aspirational or simulated, except where explicitly noted.</p>
        <FlowAnimation steps={STACK_STEPS} caption="The full path from Airflow's trigger to a scored, gated, deployed, monitored model" />
      </section>

      {CATEGORIES.map((cat) => (
        <section key={cat.name} className="card span-2">
          <h3>{cat.name}</h3>
          <div className="tool-grid">
            {cat.tools.map((tool) => (
              <article key={tool.name} className="tool-card card animate-in">
                <div className="tool-card-head">
                  <h4>{tool.name}</h4>
                </div>
                <p className="muted">{tool.role}</p>
                <p className="tool-why">{tool.why}</p>
              </article>
            ))}
          </div>
        </section>
      ))}

      <section className="card span-2">
        <h3>Docker Compose services</h3>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Service</th><th>Image / build</th><th>Port</th></tr></thead>
            <tbody>
              <tr><td><code>postgres</code></td><td className="muted">postgres:16-alpine</td><td>5480</td></tr>
              <tr><td><code>mlflow</code></td><td className="muted">ghcr.io/mlflow/mlflow:v2.17.2</td><td>5030</td></tr>
              <tr><td><code>minio</code></td><td className="muted">minio/minio:latest</td><td>9370 / 9371</td></tr>
              <tr><td><code>splunk</code></td><td className="muted">splunk/splunk:9.2</td><td>8370 / 8371 / 8372</td></tr>
              <tr><td><code>otel-collector</code></td><td className="muted">otel/opentelemetry-collector-contrib</td><td>4370 / 4371</td></tr>
              <tr><td><code>prometheus</code></td><td className="muted">prom/prometheus:v2.55.1</td><td>9300</td></tr>
              <tr><td><code>grafana</code></td><td className="muted">grafana/grafana:11.2.0</td><td>3370</td></tr>
              <tr><td><code>backend</code></td><td className="muted">./backend (FastAPI + PyTorch + scikit-learn)</td><td>8170</td></tr>
              <tr><td><code>frontend</code></td><td className="muted">./frontend (React + nginx)</td><td>3070</td></tr>
              <tr><td><code>airflow-webserver</code></td><td className="muted">apache/airflow:2.10.3-python3.11</td><td>8770</td></tr>
              <tr><td><code>airflow-scheduler</code></td><td className="muted">apache/airflow:2.10.3-python3.11</td><td>—</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

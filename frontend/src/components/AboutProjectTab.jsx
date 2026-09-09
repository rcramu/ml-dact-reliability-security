import FlowAnimation from './diagrams/FlowAnimation.jsx'
import { stackConfig } from '../config.js'

const DEMO_STEPS = [
  { id: 'ingest', label: 'Ingest', color: '#6366f1' },
  { id: 'validate', label: 'Validate', color: '#0ea5e9' },
  { id: 'train', label: 'Train (PyTorch)', color: '#7c3aed' },
  { id: 'gate', label: 'Quality gate', color: '#f59e0b' },
  { id: 'deploy', label: 'Canary deploy', color: '#059669' },
  { id: 'monitor', label: 'Monitor for drift', color: '#f97316' },
]

const MAIN_TABS = [
  { id: 'ingested-data', title: 'Ingested Data', desc: 'Raw customer records, dataset versions, and Great-Expectations-style data-quality checks' },
  { id: 'pipeline', title: 'Pipeline Runs', desc: 'The 16-stage training DAG, stage-by-stage, with SLA compliance' },
  { id: 'registry', title: 'Model Registry', desc: 'Champion/challenger versions, canary deployment timeline, rollback' },
  { id: 'monitoring', title: 'Drift & Monitoring', desc: 'Reference-vs-production PSI/KS drift detection + the decision matrix' },
  { id: 'predict', title: 'Predict', desc: 'Score a customer for churn risk against the production champion' },
  { id: 'alerts', title: 'Alerts', desc: 'Quality-gate, drift and rollback notifications, also delivered to Splunk' },
]

const KB_SECTIONS = [
  { title: 'About this Project', desc: 'Goals and scope' },
  { title: 'Concept Preview', desc: 'Illustrated concepts + flashcards' },
  { title: 'Term Glossary', desc: 'Searchable definitions' },
  { title: 'Formulas & Algorithms', desc: 'PyTorch model, quality gate, PSI/KS drift, decision matrix' },
  { title: 'Architecture', desc: 'Full platform architecture + roadmap' },
  { title: 'Explain the Code', desc: 'Repo layout and request/DAG flows' },
  { title: 'Tools & Frameworks', desc: 'Airflow, PyTorch, MLflow, Prometheus, Grafana, Splunk, MinIO, PostgreSQL, React' },
  { title: 'Check My Understanding', desc: 'Self-check quiz (7+ questions per topic)' },
]

export default function AboutProjectTab() {
  return (
    <div className="grid about-project">
      <section className="card span-2 about-hero">
        <p className="eyebrow">MLOps · Deep Learning · Continuous Training &amp; Monitoring (Production-grade)</p>
        <h2>About this project — Production ML Continuous Training Platform</h2>
        <p className="lead">
          A platform that <strong>automatically trains, evaluates, deploys, monitors, and retrains</strong> a
          PyTorch customer-churn model: Apache Airflow orchestrates a 16-stage training DAG, MLflow tracks
          every experiment and owns the Model Registry, an automated quality gate blocks any candidate that
          regresses on the current production champion, canary deployment + automatic rollback protect
          production, and a drift-vs-evaluation decision matrix triggers retraining on its own when
          production traffic drifts away from the training distribution — backed by real Prometheus,
          Grafana, Splunk, MinIO (S3) and PostgreSQL containers.
        </p>
        <div className="about-pills">
          <span className="about-pill">Airflow orchestration</span>
          <span className="about-pill">PyTorch training</span>
          <span className="about-pill">MLflow registry</span>
          <span className="about-pill">Automated quality gate</span>
          <span className="about-pill">Canary deploy + rollback</span>
          <span className="about-pill">PSI / KS drift detection</span>
          <span className="about-pill">Decision-matrix auto-retrain</span>
          <span className="about-pill">Prometheus + Grafana</span>
          <span className="about-pill">Splunk HEC</span>
          <span className="about-pill">MinIO (S3)</span>
          <span className="about-pill">FastAPI · Swagger</span>
          <span className="about-pill">React · Docker Compose</span>
        </div>
        <FlowAnimation steps={DEMO_STEPS} caption="Ingest -> validate -> train (PyTorch) -> quality gate -> canary deploy -> monitor for drift -> retrain" />
      </section>

      <section className="card">
        <h3>Scope of this build</h3>
        <ul className="compact-list">
          <li>Implements req.md's Customer Churn Prediction use case end-to-end: Phases 1-8 (local Airflow, S3/PyTorch training, MLflow registry, drift-triggered retraining, FastAPI serving, Prometheus/Grafana/Splunk, drift detection, automated retraining)</li>
          <li>Great Expectations is stood in for by a lightweight from-scratch validation module (schema, nulls, label availability, class balance, freshness) — documented in Tools &amp; Frameworks</li>
          <li>KubernetesPodOperator / EKS training and canary deployment are simulated (stage names + deployment events recorded exactly as a real rollout would produce) since this is a local docker-compose demo, not a real AWS account</li>
          <li>Terraform, GitHub Actions CI/CD, IAM/IRSA/KMS/Secrets Manager, and Trivy/Bandit security scanning are documented in the Knowledge Base as a roadmap, not run here</li>
        </ul>
      </section>

      <section className="card">
        <h3>Main menu</h3>
        <ul className="about-tab-list">
          {MAIN_TABS.map((t) => (
            <li key={t.id}><strong>{t.title}</strong> — {t.desc}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h3>Knowledge Base</h3>
        <ul className="about-tab-list">
          {KB_SECTIONS.map((t) => (
            <li key={t.title}><strong>{t.title}</strong> — {t.desc}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h3>Stack URLs</h3>
        <ul className="compact-list">
          <li>UI: <a href={stackConfig.uiUrl} target="_blank" rel="noreferrer">localhost:{stackConfig.uiPort}</a></li>
          <li>API / Swagger: <a href={`${stackConfig.apiUrl}/docs`} target="_blank" rel="noreferrer">localhost:{stackConfig.apiPort}/docs</a></li>
          <li>MLflow: <a href={stackConfig.mlflowUrl} target="_blank" rel="noreferrer">localhost:{stackConfig.mlflowPort}</a></li>
          <li>Grafana: <a href={stackConfig.grafanaUrl} target="_blank" rel="noreferrer">localhost:{stackConfig.grafanaPort}</a> (admin/admin)</li>
          <li>Prometheus: <a href={stackConfig.prometheusUrl} target="_blank" rel="noreferrer">localhost:{stackConfig.prometheusPort}</a></li>
          <li>MinIO console: <a href={stackConfig.minioConsoleUrl} target="_blank" rel="noreferrer">localhost:{stackConfig.minioConsolePort}</a></li>
          <li>Splunk: <a href={stackConfig.splunkUrl} target="_blank" rel="noreferrer">localhost:{stackConfig.splunkPort}</a></li>
          <li>Airflow: <a href={stackConfig.airflowUrl} target="_blank" rel="noreferrer">localhost:{stackConfig.airflowPort}</a> (admin/admin)</li>
        </ul>
      </section>
    </div>
  )
}

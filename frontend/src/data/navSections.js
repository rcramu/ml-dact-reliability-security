/** Production ML Continuous Training Platform — sidebar navigation sections */

export const MAIN_NAV = [
  { id: 'ingested-data', label: 'Ingested Data', description: 'Raw customer records, dataset versions, data-quality checks' },
  { id: 'pipeline', label: 'Pipeline Runs', description: 'The 16-stage training DAG, stage-by-stage, with SLA compliance' },
  { id: 'registry', label: 'Model Registry', description: 'Champion/challenger versions, canary deployment, rollback' },
  { id: 'monitoring', label: 'Drift & Monitoring', description: 'Reference-vs-production drift detection + decision matrix' },
  { id: 'predict', label: 'Predict', description: 'Score a customer for churn risk against the production champion' },
  { id: 'alerts', label: 'Alerts', description: 'Quality-gate, drift and rollback notifications (also sent to Splunk)' },
]

export const PLATFORM_NAV = [
  { id: 'api-reference', label: 'API Reference', description: 'Endpoint catalog · Swagger · ReDoc' },
]

// Order matters — "Check My Understanding" must stay last.
export const KB_NAV = [
  { id: 'kb-about', label: 'About this Project', kbSection: 'about', description: 'Vision & scope of the Continuous Training Platform' },
  { id: 'kb-concepts', label: 'Concept Preview', kbSection: 'concepts', description: 'Illustrated concepts · flashcards' },
  { id: 'kb-glossary', label: 'Term Glossary', kbSection: 'glossary', description: 'Searchable term definitions' },
  { id: 'kb-models', label: 'Formulas & Algorithms', kbSection: 'models', description: 'PyTorch model, quality gate, PSI/KS drift, decision matrix' },
  { id: 'kb-architecture', label: 'Architecture', kbSection: 'architecture', description: 'Full platform architecture · roadmap' },
  { id: 'kb-code', label: 'Explain the Code', kbSection: 'code', description: 'Repo layout · request/DAG flows' },
  { id: 'kb-tools', label: 'Tools & Frameworks', kbSection: 'tools', description: 'Airflow, PyTorch, MLflow, Prometheus, Grafana, Splunk, MinIO, PostgreSQL, React' },
  { id: 'kb-check', label: 'Check My Understanding', kbSection: 'check', description: 'Self-check quiz (7+ questions per topic)' },
]

export function isKbView(view) {
  return String(view).startsWith('kb-')
}

export function kbSectionFromView(view) {
  const item = KB_NAV.find((n) => n.id === view)
  return item?.kbSection || 'about'
}

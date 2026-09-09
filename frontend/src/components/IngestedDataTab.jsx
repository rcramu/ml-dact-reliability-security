import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { AnimatedCard } from './shared.jsx'

const TABLES = [
  { id: 'records', label: 'Ingested Customer Records', cols: ['split', 'tenure_months', 'monthly_charges', 'age', 'support_tickets_90d', 'usage_hours_week', 'is_month_to_month', 'autopay_enabled', 'has_addons', 'label'] },
  { id: 'datasets', label: 'Dataset Versions', cols: ['version', 'scenario', 'rows', 'features', 'seed', 'location'] },
  { id: 'dq', label: 'Data Quality Checks', cols: ['check_name', 'passed', 'detail'] },
  { id: 'predictions', label: 'Live Predictions', cols: ['tenure_months', 'monthly_charges', 'support_tickets_90d', 'churn_probability', 'prediction', 'ground_truth', 'latency_ms', 'profile'] },
  { id: 'audit', label: 'Audit Log', cols: ['action', 'resource_type', 'detail', 'created_at'] },
]

export default function IngestedDataTab({ setError }) {
  const [summary, setSummary] = useState(null)
  const [active, setActive] = useState('records')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [s3Objects, setS3Objects] = useState(null)
  const [s3Prefix, setS3Prefix] = useState('')

  useEffect(() => {
    api.dataSummary().then(setSummary).catch((err) => setError(err.message))
  }, [setError])

  useEffect(() => {
    setLoading(true)
    const loaders = {
      records: () => api.records(150),
      datasets: () => api.datasets(50),
      dq: () => api.dataQualityChecks(150),
      predictions: () => api.predictionsRaw(100),
      audit: () => api.auditLog(100),
    }
    loaders[active]()
      .then(setRows)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [active, setError])

  useEffect(() => {
    api.s3Objects(s3Prefix).then(setS3Objects).catch((err) => setError(err.message))
  }, [s3Prefix, setError])

  const activeTable = TABLES.find((t) => t.id === active)

  return (
    <div className="grid">
      {summary && (
        <AnimatedCard title="Ingestion summary" className="span-2">
          <div className="stat-row">
            <div className="stat-pill"><span className="stat-val">{summary.dataset_versions_count}</span><span className="stat-label">Dataset versions</span></div>
            <div className="stat-pill"><span className="stat-val">{summary.raw_records_count}</span><span className="stat-label">Ingested records</span></div>
            <div className="stat-pill"><span className="stat-val">{summary.model_versions_count}</span><span className="stat-label">Model versions</span></div>
            <div className="stat-pill"><span className="stat-val">{summary.pipeline_runs_count}</span><span className="stat-label">Pipeline runs</span></div>
            <div className="stat-pill"><span className="stat-val">{summary.production_predictions_count}</span><span className="stat-label">Predictions served</span></div>
            <div className="stat-pill"><span className="stat-val">{summary.drift_checks_count}</span><span className="stat-label">Drift checks</span></div>
            <div className="stat-pill"><span className="stat-val">{summary.alerts_count}</span><span className="stat-label">Alerts</span></div>
            <div className="stat-pill"><span className="stat-val">{summary.audit_logs_count}</span><span className="stat-label">Audit entries</span></div>
          </div>
        </AnimatedCard>
      )}

      <AnimatedCard title="Browse ingested tables" className="span-2">
        <p className="muted">The raw customer data every training run learns from — generated deterministically per scenario so results reproduce exactly across restarts.</p>
        <div className="uc-topic-filters">
          {TABLES.map((t) => (
            <button key={t.id} type="button" className={active === t.id ? 'uc-topic active' : 'uc-topic'} onClick={() => setActive(t.id)}>{t.label}</button>
          ))}
        </div>

        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div className="ingest-table-wrap">
            <table className="data-table">
              <thead><tr>{activeTable.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={row.id || i}>
                    {activeTable.cols.map((c) => (
                      <td key={c}>{typeof row[c] === 'boolean' ? String(row[c]) : (row[c] ?? '—')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted glossary-count">{rows.length} rows shown (sample)</p>
          </div>
        )}
      </AnimatedCard>

      <AnimatedCard title="MinIO / S3 objects" className="span-2">
        <p className="muted">Every dataset version is also written to S3-compatible object storage (MinIO stands in for Amazon S3).</p>
        <div className="slo-form">
          <label>Prefix filter
            <input type="text" placeholder="e.g. datasets/customer-churn/" value={s3Prefix} onChange={(e) => setS3Prefix(e.target.value)} />
          </label>
        </div>
        {s3Objects && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Key</th><th>Size (bytes)</th><th>Last modified</th></tr></thead>
              <tbody>
                {s3Objects.map((o) => (
                  <tr key={o.key}><td><code>{o.key}</code></td><td>{o.size}</td><td className="muted">{new Date(o.last_modified).toLocaleString()}</td></tr>
                ))}
              </tbody>
            </table>
            {s3Objects.length === 0 && <p className="muted">No objects under this prefix yet.</p>}
          </div>
        )}
      </AnimatedCard>
    </div>
  )
}

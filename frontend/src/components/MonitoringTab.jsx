import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { AnimatedCard } from './shared.jsx'

const STATUS_TONE = { GREEN: 'ok', NORMAL: 'ok', WARNING: 'warn', CRITICAL: 'bad' }
function StatusPill({ status }) {
  return <span className={`severity-badge severity-${STATUS_TONE[status] || 'ok'}`}>{status}</span>
}

const PROFILES = [
  { id: 'stable', label: 'Stable traffic' },
  { id: 'drifted', label: 'Drifted traffic' },
  { id: 'severe_drift', label: 'Severe drift' },
]

export default function MonitoringTab({ setError }) {
  const [history, setHistory] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [selected, setSelected] = useState(null)
  const [profile, setProfile] = useState('drifted')
  const [checking, setChecking] = useState(false)

  const loadHistory = useCallback(() => {
    api.monitoringHistory(50).then(setHistory).catch((err) => setError(err.message))
  }, [setError])

  useEffect(() => { loadHistory() }, [loadHistory])
  useEffect(() => { api.decisionMatrix().then(setMatrix).catch((err) => setError(err.message)) }, [setError])

  const runCheck = async () => {
    setChecking(true)
    try {
      const check = await api.triggerMonitoringCheck({ profile, auto_retrain: true })
      loadHistory()
      setSelected(check)
    } catch (err) { setError(err.message) } finally { setChecking(false) }
  }

  const openCheck = async (id) => {
    try { setSelected(await api.monitoringDetail(id)) } catch (err) { setError(err.message) }
  }

  return (
    <div className="grid">
      <AnimatedCard title="Run a drift + evaluation check" className="span-2">
        <p className="muted">Compares the champion's training distribution against a simulated batch of production traffic (PSI + KS per feature), then combines that with a production-performance signal via the decision matrix below. When drift is HIGH and quality is not confirmed GOOD, retraining is triggered automatically.</p>
        <div className="uc-topic-filters">
          {PROFILES.map((p) => (
            <button key={p.id} type="button" className={profile === p.id ? 'uc-topic active' : 'uc-topic'} onClick={() => setProfile(p.id)}>{p.label}</button>
          ))}
        </div>
        <button type="button" className="primary-btn" onClick={runCheck} disabled={checking}>
          {checking ? 'Checking…' : `Run check (${profile})`}
        </button>
      </AnimatedCard>

      {matrix && (
        <AnimatedCard title="Drift × evaluation decision matrix" className="span-2">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Drift level</th><th>Evaluation level</th><th>Overall status</th><th>Recommended action</th></tr></thead>
              <tbody>
                {matrix.map((row) => (
                  <tr key={`${row.drift_level}-${row.evaluation_level}`}>
                    <td>{row.drift_level}</td>
                    <td>{row.evaluation_level}</td>
                    <td><StatusPill status={row.overall_status} /></td>
                    <td className="muted">{row.recommended_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AnimatedCard>
      )}

      <AnimatedCard title={`${history ? history.length : 0} drift checks`} className="span-2">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Drift</th><th>Evaluation</th><th>Overall</th><th>Max PSI</th><th>Prod. accuracy</th><th>Auto-retrain</th><th>When</th><th></th></tr></thead>
            <tbody>
              {(history || []).map((c) => (
                <tr key={c.id}>
                  <td>{c.drift_level}</td>
                  <td>{c.evaluation_level}</td>
                  <td><StatusPill status={c.overall_status} /></td>
                  <td>{c.max_psi}</td>
                  <td>{c.production_accuracy != null ? `${(c.production_accuracy * 100).toFixed(1)}%` : '—'}</td>
                  <td>{c.triggered_retrain ? '✅' : '—'}</td>
                  <td className="muted">{new Date(c.created_at).toLocaleString()}</td>
                  <td><button type="button" className="ghost-btn" onClick={() => openCheck(c.id)}>Per-feature</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AnimatedCard>

      {selected && (
        <AnimatedCard title={`Check ${selected.id.slice(0, 8)} — per-feature PSI/KS`} className="span-2">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Feature</th><th>PSI</th><th>KS statistic</th><th>KS p-value</th><th>Reference mean</th><th>Production mean</th><th>Status</th></tr></thead>
              <tbody>
                {(selected.feature_results || []).map((f) => (
                  <tr key={f.feature_name}>
                    <td>{f.feature_name}</td>
                    <td>{f.psi}</td>
                    <td>{f.ks_statistic}</td>
                    <td>{f.ks_pvalue}</td>
                    <td>{f.reference_mean}</td>
                    <td>{f.production_mean}</td>
                    <td><StatusPill status={f.status === 'CRITICAL' ? 'CRITICAL' : f.status === 'WARNING' ? 'WARNING' : 'GREEN'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AnimatedCard>
      )}
    </div>
  )
}

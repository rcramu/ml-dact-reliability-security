import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { AnimatedCard } from './shared.jsx'

const STATUS_TONE = { SUCCESS: 'ok', PROMOTED: 'ok', RUNNING: 'warn', PENDING: 'warn', REJECTED: 'bad', BLOCKED: 'bad', FAILED: 'bad', SKIPPED: 'warn' }
function StatusPill({ status }) {
  return <span className={`severity-badge severity-${STATUS_TONE[status] || 'ok'}`}>{status}</span>
}

const SCENARIOS = ['healthy', 'volume_anomaly', 'feature_drift', 'label_imbalance', 'regression']

export default function PipelineTab({ setError }) {
  const [runs, setRuns] = useState(null)
  const [selected, setSelected] = useState(null)
  const [sla, setSla] = useState(null)
  const [scenario, setScenario] = useState('healthy')
  const [triggering, setTriggering] = useState(false)

  const loadRuns = useCallback(() => {
    api.trainingHistory(50).then(setRuns).catch((err) => setError(err.message))
  }, [setError])

  useEffect(() => { loadRuns() }, [loadRuns])
  useEffect(() => { api.sla().then(setSla).catch((err) => setError(err.message)) }, [setError])

  const openRun = async (runId) => {
    try {
      setSelected(await api.trainingStatus(runId))
    } catch (err) { setError(err.message) }
  }

  const triggerRun = async () => {
    setTriggering(true)
    try {
      const run = await api.triggerTraining({ trigger_type: 'manual', scenario, trigger_detail: `Manual trigger from UI (${scenario})` })
      loadRuns()
      setSelected(run)
    } catch (err) { setError(err.message) } finally { setTriggering(false) }
  }

  return (
    <div className="grid">
      <AnimatedCard title="Trigger a training run" className="span-2">
        <p className="muted">Runs the same 16-stage DAG Airflow triggers on a schedule (see <code>airflow/dags/training_pipeline_dag.py</code>).</p>
        <div className="uc-topic-filters">
          {SCENARIOS.map((s) => (
            <button key={s} type="button" className={scenario === s ? 'uc-topic active' : 'uc-topic'} onClick={() => setScenario(s)}>{s}</button>
          ))}
        </div>
        <button type="button" className="primary-btn" onClick={triggerRun} disabled={triggering}>
          {triggering ? 'Training…' : `Run training (${scenario})`}
        </button>
      </AnimatedCard>

      {sla && (
        <AnimatedCard title={`SLA compliance: ${sla.compliance_pct}%`} className="span-2">
          <p className="muted">{sla.runs_with_violation} / {sla.total_runs} runs had at least one stage exceed its SLA budget.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Stage</th><th>Actual (min)</th><th>Budget (min)</th><th>Run</th></tr></thead>
              <tbody>
                {sla.violations.slice(0, 10).map((v) => (
                  <tr key={v.id}><td>{v.stage_name}</td><td>{v.actual_minutes}</td><td>{v.max_minutes}</td><td className="muted"><code>{v.run_id.slice(0, 8)}</code></td></tr>
                ))}
              </tbody>
            </table>
            {sla.violations.length === 0 && <p className="muted">No SLA violations recorded.</p>}
          </div>
        </AnimatedCard>
      )}

      <AnimatedCard title={`${runs ? runs.length : 0} training runs`} className="span-2">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Trigger</th><th>Scenario / detail</th><th>Status</th><th>Outcome</th><th>Started</th><th></th></tr></thead>
            <tbody>
              {(runs || []).map((r) => (
                <tr key={r.id}>
                  <td>{r.trigger_type}</td>
                  <td className="muted">{r.trigger_detail}</td>
                  <td><StatusPill status={r.status} /></td>
                  <td>{r.outcome || '—'}</td>
                  <td className="muted">{new Date(r.started_at).toLocaleString()}</td>
                  <td><button type="button" className="ghost-btn" onClick={() => openRun(r.id)}>View stages</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AnimatedCard>

      {selected && (
        <AnimatedCard title={`Run ${selected.id.slice(0, 8)} — ${selected.stages_success}/${selected.stage_count} stages succeeded`} className="span-2">
          <ol className="code-flow-list">
            {selected.stages.map((s) => (
              <li key={s.stage_name} className={`code-flow-step ${s.status === 'RUNNING' ? 'active' : ''}`}>
                <span className="code-flow-num">{s.stage_order + 1}</span>
                <p>
                  <strong>{s.stage_name}</strong> — <StatusPill status={s.status} /> ({s.simulated_minutes} min)
                  {Object.keys(s.detail || {}).length > 0 && (
                    <span className="muted"> — {JSON.stringify(s.detail)}</span>
                  )}
                </p>
              </li>
            ))}
          </ol>
        </AnimatedCard>
      )}
    </div>
  )
}

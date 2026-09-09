import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { AnimatedCard } from './shared.jsx'

const STAGE_TONE = { production: 'ok', candidate: 'warn', archived: 'warn', rejected: 'bad', rolled_back: 'bad' }
function StagePill({ stage }) {
  return <span className={`severity-badge severity-${STAGE_TONE[stage] || 'ok'}`}>{stage}</span>
}

export default function RegistryTab({ setError }) {
  const [model, setModel] = useState(null)
  const [versions, setVersions] = useState(null)
  const [deployment, setDeployment] = useState(null)
  const [rollingBack, setRollingBack] = useState(false)

  const load = useCallback(async () => {
    try {
      const models = await api.models()
      setModel(models[0])
      setVersions(await api.versions(50))
      setDeployment(await api.deployment())
    } catch (err) { setError(err.message) }
  }, [setError])

  useEffect(() => { load() }, [load])

  const doRollback = async () => {
    setRollingBack(true)
    try {
      await api.rollback('Manual rollback requested from UI')
      load()
    } catch (err) { setError(err.message) } finally { setRollingBack(false) }
  }

  return (
    <div className="grid">
      {model && (
        <AnimatedCard title={model.name} className="span-2">
          <p>{model.description}</p>
          <div className="stat-row">
            <div className="stat-pill"><span className="stat-val">{model.version_count}</span><span className="stat-label">Versions</span></div>
            <div className="stat-pill"><span className="stat-val">{model.run_count}</span><span className="stat-label">Training runs</span></div>
            {model.champion && <div className="stat-pill"><span className="stat-val">v{model.champion.version}</span><span className="stat-label">Champion</span></div>}
            {model.champion && <div className="stat-pill"><span className="stat-val">{(model.champion.test_f1 * 100).toFixed(1)}%</span><span className="stat-label">Test F1</span></div>}
          </div>
          {model.champion && (
            <button type="button" className="ghost-btn" onClick={doRollback} disabled={rollingBack}>
              {rollingBack ? 'Rolling back…' : 'Roll back to previous production version'}
            </button>
          )}
        </AnimatedCard>
      )}

      <AnimatedCard title={`${versions ? versions.length : 0} model versions`} className="span-2">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Version</th><th>Stage</th><th>Test F1</th><th>Precision</th><th>Recall</th><th>ROC-AUC</th><th>Registry v</th></tr></thead>
            <tbody>
              {(versions || []).map((v) => (
                <tr key={v.id}>
                  <td>v{v.version} {v.is_champion && '⭐'}</td>
                  <td><StagePill stage={v.stage} /></td>
                  <td>{(v.test_f1 * 100).toFixed(1)}%</td>
                  <td>{(v.precision * 100).toFixed(1)}%</td>
                  <td>{(v.recall * 100).toFixed(1)}%</td>
                  <td>{(v.roc_auc * 100).toFixed(1)}%</td>
                  <td className="muted">{v.registry_version ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AnimatedCard>

      {deployment && (
        <AnimatedCard title="Deployment / canary timeline" className="span-2">
          <p className="muted">Every promotion walks through the same simulated canary rollout (KubernetesPodOperator → EKS): stage → smoke_test → canary_5 → canary_25 → canary_50 → canary_100 → production.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Stage</th><th>Status</th><th>Detail</th><th>When</th></tr></thead>
              <tbody>
                {deployment.events.slice(0, 30).map((e) => (
                  <tr key={e.id}><td>{e.stage}</td><td>{e.status}</td><td className="muted">{e.detail}</td><td className="muted">{new Date(e.created_at).toLocaleString()}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          {deployment.rollbacks.length > 0 && (
            <>
              <h4>Rollback history</h4>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>From</th><th>To</th><th>Reason</th><th>Triggered by</th></tr></thead>
                  <tbody>
                    {deployment.rollbacks.map((r) => (
                      <tr key={r.id}><td>v{r.from_version}</td><td>v{r.to_version}</td><td className="muted">{r.reason}</td><td>{r.triggered_by}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </AnimatedCard>
      )}
    </div>
  )
}

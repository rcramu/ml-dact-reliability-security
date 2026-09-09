import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { AnimatedCard } from './shared.jsx'

const DEFAULT_FORM = {
  tenure_months: 12, monthly_charges: 70, age: 35, support_tickets_90d: 1,
  usage_hours_week: 12, is_month_to_month: false, autopay_enabled: true, has_addons: false,
}

export default function PredictTab({ setError }) {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [result, setResult] = useState(null)
  const [scoring, setScoring] = useState(false)
  const [history, setHistory] = useState(null)

  const loadHistory = () => api.predictHistory(20).then(setHistory).catch((err) => setError(err.message))
  useEffect(() => { loadHistory() }, [])

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }))

  const submit = async (e) => {
    e.preventDefault()
    setScoring(true)
    try {
      setResult(await api.predict(form))
      loadHistory()
    } catch (err) { setError(err.message) } finally { setScoring(false) }
  }

  return (
    <div className="grid">
      <AnimatedCard title="Score a customer for churn risk" className="span-2">
        <p className="muted">Calls <code>POST /api/v1/models/customer-churn/predict</code> against the current production champion — the same endpoint req.md's inference API describes.</p>
        <form className="slo-form" onSubmit={submit}>
          <label>Tenure (months)
            <input type="number" min="0" value={form.tenure_months} onChange={(e) => setField('tenure_months', Number(e.target.value))} />
          </label>
          <label>Monthly charges ($)
            <input type="number" min="0" step="0.01" value={form.monthly_charges} onChange={(e) => setField('monthly_charges', Number(e.target.value))} />
          </label>
          <label>Age
            <input type="number" min="18" value={form.age} onChange={(e) => setField('age', Number(e.target.value))} />
          </label>
          <label>Support tickets (last 90d)
            <input type="number" min="0" value={form.support_tickets_90d} onChange={(e) => setField('support_tickets_90d', Number(e.target.value))} />
          </label>
          <label>Usage hours / week
            <input type="number" min="0" step="0.1" value={form.usage_hours_week} onChange={(e) => setField('usage_hours_week', Number(e.target.value))} />
          </label>
          <label><input type="checkbox" checked={form.is_month_to_month} onChange={(e) => setField('is_month_to_month', e.target.checked)} /> Month-to-month contract</label>
          <label><input type="checkbox" checked={form.autopay_enabled} onChange={(e) => setField('autopay_enabled', e.target.checked)} /> Autopay enabled</label>
          <label><input type="checkbox" checked={form.has_addons} onChange={(e) => setField('has_addons', e.target.checked)} /> Has add-on services</label>
          <button type="submit" className="primary-btn" disabled={scoring}>{scoring ? 'Scoring…' : 'Predict churn risk'}</button>
        </form>
      </AnimatedCard>

      {result && (
        <AnimatedCard title="Prediction result" className="span-2">
          <div className="stat-row">
            <div className="stat-pill"><span className="stat-val">{result.prediction === 1 ? 'Churn' : 'Retain'}</span><span className="stat-label">Prediction</span></div>
            <div className="stat-pill"><span className="stat-val">{(result.churn_probability * 100).toFixed(1)}%</span><span className="stat-label">Churn probability</span></div>
            <div className="stat-pill"><span className="stat-val">v{result.model_version}</span><span className="stat-label">Model version</span></div>
            <div className="stat-pill"><span className="stat-val">{result.decision_threshold}</span><span className="stat-label">Decision threshold</span></div>
            <div className="stat-pill"><span className="stat-val">{result.latency_ms} ms</span><span className="stat-label">Latency</span></div>
          </div>
        </AnimatedCard>
      )}

      <AnimatedCard title={`${history ? history.length : 0} recent live predictions`} className="span-2">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Tenure</th><th>Monthly $</th><th>Tickets</th><th>Probability</th><th>Prediction</th><th>Latency</th><th>When</th></tr></thead>
            <tbody>
              {(history || []).map((p) => (
                <tr key={p.id}>
                  <td>{p.tenure_months}</td>
                  <td>{p.monthly_charges}</td>
                  <td>{p.support_tickets_90d}</td>
                  <td>{(p.churn_probability * 100).toFixed(1)}%</td>
                  <td>{p.prediction === 1 ? 'Churn' : 'Retain'}</td>
                  <td>{p.latency_ms} ms</td>
                  <td className="muted">{new Date(p.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AnimatedCard>
    </div>
  )
}

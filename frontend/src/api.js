import { MODEL_NAME } from './config.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = data.detail
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail) || res.statusText
    throw new Error(message)
  }
  return data
}

const m = MODEL_NAME

export const api = {
  ready: () => request('/ready'),

  dataSummary: () => request('/data/summary'),
  datasets: (limit = 50) => request(`/data/datasets?limit=${limit}`),
  records: (limit = 100, params = {}) => {
    const qs = new URLSearchParams({ limit, ...params }).toString()
    return request(`/data/records?${qs}`)
  },
  dataQualityChecks: (limit = 100) => request(`/data/data-quality-checks?limit=${limit}`),
  predictionsRaw: (limit = 100) => request(`/data/predictions?limit=${limit}`),
  s3Objects: (prefix = '') => request(`/data/s3-objects?prefix=${encodeURIComponent(prefix)}`),
  auditLog: (limit = 100) => request(`/data/audit-log?limit=${limit}`),
  seedScenarios: () => request('/data/seed-scenarios'),

  models: () => request('/api/v1/models'),
  versions: (limit = 100) => request(`/api/v1/models/${m}/versions?limit=${limit}`),
  deployment: () => request(`/api/v1/models/${m}/deployment`),
  rollback: (reason) => request(`/api/v1/models/${m}/rollback`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }),
  }),

  triggerTraining: (body) => request(`/api/v1/models/${m}/training`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  trainingHistory: (limit = 50) => request(`/api/v1/models/${m}/training/history?limit=${limit}`),
  trainingStatus: (runId) => request(`/api/v1/models/${m}/training/${runId}`),
  evaluationDetail: (runId) => request(`/api/v1/models/${m}/evaluation/${runId}`),

  pipelineRuns: (limit = 50) => request(`/pipeline/runs?limit=${limit}`),
  pipelineRunDetail: (runId) => request(`/pipeline/runs/${runId}`),
  sla: () => request('/pipeline/sla'),

  triggerMonitoringCheck: (body) => request(`/api/v1/models/${m}/monitoring/check`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  monitoringHistory: (limit = 50) => request(`/api/v1/models/${m}/monitoring/history?limit=${limit}`),
  monitoringDetail: (checkId) => request(`/api/v1/models/${m}/monitoring/${checkId}`),
  decisionMatrix: () => request(`/api/v1/models/${m}/monitoring/decision-matrix`),

  predict: (body) => request(`/api/v1/models/${m}/predict`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  predictHistory: (limit = 50) => request(`/api/v1/models/${m}/predict/history?limit=${limit}`),

  alerts: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/alerts${qs ? `?${qs}` : ''}`)
  },
  resolveAlert: (alertId) => request(`/alerts/${encodeURIComponent(alertId)}/resolve`, { method: 'POST' }),

  audit: (limit = 100) => request(`/audit?limit=${limit}`),

  catalog: () => request('/docs-catalog'),
}

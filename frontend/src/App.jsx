import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { stackConfig } from './config.js'
import { StatusDot } from './components/shared.jsx'
import AppSidebar from './components/AppSidebar.jsx'
import IngestedDataTab from './components/IngestedDataTab.jsx'
import PipelineTab from './components/PipelineTab.jsx'
import RegistryTab from './components/RegistryTab.jsx'
import MonitoringTab from './components/MonitoringTab.jsx'
import PredictTab from './components/PredictTab.jsx'
import AlertsTab from './components/AlertsTab.jsx'
import ApiReferenceTab from './components/ApiReferenceTab.jsx'
import KnowledgeBasePanel from './components/KnowledgeBasePanel.jsx'
import AbbreviationStrip from './components/AbbreviationStrip.jsx'
import { AnimationProvider, useAnimationControl } from './context/AnimationContext.jsx'
import { MAIN_NAV, PLATFORM_NAV, KB_NAV, isKbView, kbSectionFromView } from './data/navSections.js'

const VIEW_TITLES = Object.fromEntries([
  ...MAIN_NAV.map((n) => [n.id, n.label]),
  ...PLATFORM_NAV.map((n) => [n.id, n.label]),
  ...KB_NAV.map((n) => [n.id, n.label]),
])

function AppShell() {
  const [view, setView] = useState('ingested-data')
  const [kbSection, setKbSection] = useState('about')
  const [ready, setReady] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const { paused, setPaused } = useAnimationControl()

  const refresh = useCallback(async () => {
    setError('')
    try {
      setReady(await api.ready())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const onSidebarNavigate = useCallback((id) => {
    setView(id)
    if (isKbView(id)) setKbSection(kbSectionFromView(id))
  }, [])

  const panelTitle = VIEW_TITLES[view] || 'Production ML Continuous Training Platform'

  function renderMain() {
    if (view === 'ingested-data') return <IngestedDataTab setError={setError} />
    if (view === 'pipeline') return <PipelineTab setError={setError} />
    if (view === 'registry') return <RegistryTab setError={setError} />
    if (view === 'monitoring') return <MonitoringTab setError={setError} />
    if (view === 'predict') return <PredictTab setError={setError} />
    if (view === 'alerts') return <AlertsTab setError={setError} />
    if (view === 'api-reference') return <ApiReferenceTab setError={setError} />
    if (isKbView(view)) {
      return <KnowledgeBasePanel setError={setError} section={kbSection} setSection={setKbSection} />
    }
    return <IngestedDataTab setError={setError} />
  }

  return (
    <div className="app app-with-sidebar">
      <header className="hero">
        <div>
          <p className="eyebrow">Track 8 · MLOps Platform · Airflow + PyTorch + MLflow</p>
          <h1>Production ML Continuous Training Platform</h1>
          <p className="subtitle">Customer churn prediction · automated training DAG · quality gate · canary deploy · drift-triggered retraining</p>
        </div>
        <div className="hero-status">
          {ready && (
            <>
              <StatusDot ok={ready.database} label="Database" />
              <StatusDot ok={ready.models_seeded > 0} label="Model seeded" />
              <StatusDot ok={ready.versions_seeded > 0} label="Champion trained" />
              <StatusDot ok={ready.ready} label="Ready" />
            </>
          )}
        </div>
      </header>

      <div className="app-toolbar">
        <span className="panel-title">{panelTitle}</span>
        <label className="tab ghost pause-toggle toolbar-action">
          <input type="checkbox" checked={paused} onChange={(e) => setPaused(e.target.checked)} />
          Pause animations
        </label>
        <button type="button" className="tab ghost refresh toolbar-action" onClick={refresh}>Refresh</button>
      </div>

      {error && <div className="alert">{error}</div>}

      {loading ? (
        <p className="muted">Connecting to API…</p>
      ) : (
        <div className="app-body">
          <AppSidebar view={view} onNavigate={onSidebarNavigate} />
          <main className="app-main">{renderMain()}</main>
        </div>
      )}

      <footer className="foot">
        Swagger: <a href={`${stackConfig.apiUrl}/docs`} target="_blank" rel="noreferrer">/docs</a>
        {' · '}
        <a href={`${stackConfig.apiUrl}/redoc`} target="_blank" rel="noreferrer">ReDoc</a>
        {' · '}
        MLflow: <a href={stackConfig.mlflowUrl} target="_blank" rel="noreferrer">:{stackConfig.mlflowPort}</a>
        {' · '}
        Grafana: <a href={stackConfig.grafanaUrl} target="_blank" rel="noreferrer">:{stackConfig.grafanaPort}</a>
        {' · '}
        Prometheus: <a href={stackConfig.prometheusUrl} target="_blank" rel="noreferrer">:{stackConfig.prometheusPort}</a>
        {' · '}
        MinIO: <a href={stackConfig.minioConsoleUrl} target="_blank" rel="noreferrer">:{stackConfig.minioConsolePort}</a>
        {' · '}
        Splunk: <a href={stackConfig.splunkUrl} target="_blank" rel="noreferrer">:{stackConfig.splunkPort}</a>
        {' · '}
        Airflow: <a href={stackConfig.airflowUrl} target="_blank" rel="noreferrer">:{stackConfig.airflowPort}</a>
      </footer>
      <AbbreviationStrip />
    </div>
  )
}

export default function App() {
  return (
    <AnimationProvider>
      <AppShell />
    </AnimationProvider>
  )
}

import { useState } from 'react'
import FlowAnimation from './diagrams/FlowAnimation.jsx'
import ConceptFlashcards from './ConceptFlashcards.jsx'
import { CONCEPTS } from '../data/conceptPreview.js'

const STEP_SETS = {
  airflow: [
    { id: 'schedule', label: 'Schedule / event', color: '#94a3b8' },
    { id: 'dag', label: 'Airflow DAG', color: '#0ea5e9' },
    { id: 'api', label: 'Call backend API', color: '#6366f1' },
    { id: 'inspect', label: 'Inspect result', color: '#f59e0b' },
    { id: 'alert', label: 'Alert if needed', color: '#059669' },
  ],
  training_dag: [
    { id: 'data', label: 'check_new_dataset', color: '#94a3b8' },
    { id: 'validate', label: 'validate_data', color: '#0ea5e9' },
    { id: 'train', label: 'train_pytorch', color: '#6366f1' },
    { id: 'gate', label: 'quality_gate', color: '#f59e0b' },
    { id: 'deploy', label: 'deploy_production', color: '#059669' },
  ],
  quality_gate: [
    { id: 'candidate', label: 'Candidate metrics', color: '#94a3b8' },
    { id: 'floor', label: 'Absolute floors', color: '#0ea5e9' },
    { id: 'compare', label: 'vs. champion F1', color: '#6366f1' },
    { id: 'result', label: 'PASS / FAIL', color: '#f59e0b' },
    { id: 'action', label: 'Register or reject', color: '#059669' },
  ],
  mlflow_registry: [
    { id: 'run', label: 'MLflow run logged', color: '#94a3b8' },
    { id: 'gate', label: 'Quality gate PASS?', color: '#0ea5e9' },
    { id: 'register', label: 'create_model_version', color: '#6366f1' },
    { id: 'stage', label: 'Transition stage', color: '#f59e0b' },
    { id: 'prod', label: 'Production / Archived', color: '#059669' },
  ],
  canary_deploy: [
    { id: 'stage', label: 'stage', color: '#94a3b8' },
    { id: 'smoke', label: 'smoke_test', color: '#0ea5e9' },
    { id: 'canary', label: 'canary_5/25/50/100', color: '#6366f1' },
    { id: 'prod', label: 'production', color: '#f59e0b' },
    { id: 'rollback', label: 'rollback (if needed)', color: '#f87171' },
  ],
  drift_detection: [
    { id: 'ref', label: 'Reference (training)', color: '#94a3b8' },
    { id: 'prod', label: 'Production batch', color: '#0ea5e9' },
    { id: 'psi', label: 'PSI + KS per feature', color: '#6366f1' },
    { id: 'classify', label: 'GREEN/WARNING/CRITICAL', color: '#f59e0b' },
    { id: 'level', label: 'Drift level LOW/HIGH', color: '#059669' },
  ],
  decision_matrix: [
    { id: 'drift', label: 'Drift level', color: '#94a3b8' },
    { id: 'eval', label: 'Evaluation level', color: '#0ea5e9' },
    { id: 'matrix', label: '6-outcome matrix', color: '#6366f1' },
    { id: 'status', label: 'Overall status', color: '#f59e0b' },
    { id: 'retrain', label: 'Auto-retrain?', color: '#059669' },
  ],
}

export default function ConceptPreviewTab() {
  const [activeId, setActiveId] = useState(CONCEPTS[0].id)
  const active = CONCEPTS.find((c) => c.id === activeId) || CONCEPTS[0]

  return (
    <div className="grid concept-preview">
      <section className="card span-2 concept-preview-hero">
        <p className="eyebrow">Before you dive in</p>
        <h2>Concept preview — Continuous Training Platform</h2>
        <p className="lead">
          Seven bite-sized illustrated concepts that explain how this platform automatically trains,
          gates, deploys, monitors, and retrains a churn-prediction model — Airflow orchestration, the
          16-stage training DAG, the automated quality gate, MLflow tracking &amp; registry, canary
          deployment &amp; rollback, PSI/KS drift detection, and the drift × evaluation decision matrix.
        </p>
      </section>

      <section className="card span-2 concept-preview-nav">
        <div className="concept-chip-row" role="tablist" aria-label="Concept topics">
          {CONCEPTS.map((concept) => (
            <button
              key={concept.id}
              type="button"
              role="tab"
              aria-selected={activeId === concept.id}
              className={activeId === concept.id ? 'concept-chip active' : 'concept-chip'}
              onClick={() => setActiveId(concept.id)}
            >
              {concept.title}
            </button>
          ))}
        </div>
      </section>

      {active && (
        <section className="card span-2 concept-preview-detail" key={active.id}>
          <header className="concept-preview-detail-head">
            <div>
              <span className="concept-preview-subtitle">{active.subtitle}</span>
              <h3>{active.title}</h3>
            </div>
          </header>

          <div className="concept-preview-illustration">
            <FlowAnimation steps={STEP_SETS[active.illustration] || STEP_SETS.training_dag} />
          </div>

          <p className="concept-preview-summary">{active.summary}</p>

          {active.flashcard?.takeaway && (
            <blockquote className="concept-pull-quote">
              <span className="concept-pull-label">Key takeaway</span>
              {active.flashcard.takeaway}
            </blockquote>
          )}

          {active.example && (
            <article className="concept-example-card">
              <h4>{active.example.title}</h4>
              <ol>
                {active.example.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </article>
          )}
        </section>
      )}

      <section className="card span-2 concept-flashdeck-section">
        <ConceptFlashcards concepts={CONCEPTS} activeId={activeId} onSelect={setActiveId} />
      </section>
    </div>
  )
}

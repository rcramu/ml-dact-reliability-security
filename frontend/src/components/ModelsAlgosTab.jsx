import FlowAnimation from './diagrams/FlowAnimation.jsx'

const PIPELINE_STEPS = [
  { id: 'data', label: 'Churn features (8)', color: '#6366f1' },
  { id: 'mlp', label: 'ChurnMLP', color: '#0ea5e9' },
  { id: 'loss', label: 'BCEWithLogitsLoss', color: '#f59e0b' },
  { id: 'gate', label: 'Quality gate', color: '#059669' },
]

const FORMULA_SECTIONS = [
  {
    id: 'churn_mlp',
    title: 'ChurnMLP — PyTorch model architecture',
    formula:
`x  (8 standardized features)
h1 = ReLU(W1.x + b1)      (16 units)
h2 = ReLU(W2.h1 + b2)     (8 units)
logit = W3.h2 + b3        (1 unit, raw score)
churn_probability = sigmoid(logit)`,
    algorithm: 'A small feed-forward MLP trained from scratch per pipeline run (no pretrained weights) — deliberately simple, fast enough to retrain on every DAG execution.',
    metrics: ['8 input features -> 16 -> 8 -> 1 output'],
  },
  {
    id: 'loss_fn',
    title: 'Class-balanced training loss',
    formula:
`pos_weight = n_negative / n_positive
loss = BCEWithLogitsLoss(pos_weight=pos_weight)
optimizer = Adam(lr=0.01), 120 epochs, batch_size=32`,
    algorithm: 'Churn is imbalanced (~24% positive in the healthy scenario); pos_weight rebalances the loss so the model doesn\'t collapse to always predicting "no churn".',
    metrics: ['final_train_loss logged to MLflow every run'],
  },
  {
    id: 'threshold',
    title: 'Decision threshold tuning',
    formula:
`for t in linspace(0.05, 0.95, 37):
    f1(t) = F1(predictions >= t, y_true)
best_threshold = argmax_t f1(t)   # tuned on the VALIDATION split`,
    algorithm: 'A naive 0.5 cutoff is rarely well-calibrated for an imbalanced problem — the threshold is tuned to maximize F1 on validation data, then reused unchanged on the test split and in production.',
    metrics: ['decision_threshold stored per ModelVersion'],
  },
  {
    id: 'gate_math',
    title: 'Quality gate (req.md\'s worked AUC example, generalized)',
    formula:
`PASS requires ALL of:
  candidate.f1        >= minimum_f1        (0.65)
  candidate.recall     >= minimum_recall    (0.55)
  candidate.precision  >= minimum_precision (0.55)

regression_pct = (champion.f1 - candidate.f1) / champion.f1 * 100
PASS also requires: regression_pct <= max_regression_pct (10%)`,
    algorithm: 'Both absolute floors AND a relative regression check must pass — a candidate can clear every floor and still be rejected for silently underperforming the current champion.',
    metrics: ['gate_result ∈ {PASS, FAIL}, regression_pct'],
  },
  {
    id: 'classification_metrics',
    title: 'Classification metrics (scikit-learn)',
    formula:
`precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2 * precision * recall / (precision + recall)
ROC-AUC   = area under the ROC curve
PR-AUC    = area under the precision-recall curve`,
    algorithm: 'Computed on train/val/test splits every run — train_f1 shows learning capacity, val_f1 drives threshold tuning, test_f1 is the number the quality gate actually judges.',
    metrics: ['accuracy, precision, recall, f1, roc_auc, pr_auc'],
  },
  {
    id: 'psi_formula',
    title: 'Population Stability Index (PSI) — drift detection',
    formula:
`bins  = decile quantiles of the REFERENCE (training) distribution
PSI   = sum over bins of:
          (prod_pct - ref_pct) * ln(prod_pct / ref_pct)

PSI < 0.10   -> GREEN  (no meaningful drift)
0.10 - 0.25  -> WARNING
PSI >= 0.25  -> CRITICAL`,
    algorithm: 'Bins are fixed from the REFERENCE distribution\'s quantiles, so PSI measures how production traffic has moved relative to what the model was trained on — not a symmetric two-sample statistic.',
    metrics: ['psi per feature, max_psi per drift check'],
  },
  {
    id: 'ks_formula',
    title: 'Kolmogorov-Smirnov (KS) test',
    formula:
`D = max_x | CDF_reference(x) - CDF_production(x) |
p_value = probability of observing D by chance if both samples came from the same distribution`,
    algorithm: 'Reported alongside PSI for extra statistical rigor — a small p-value alongside a large PSI is strong corroborating evidence of real drift, not sampling noise.',
    metrics: ['ks_statistic, ks_pvalue per feature'],
  },
  {
    id: 'decision_matrix_formula',
    title: 'Drift × evaluation decision matrix',
    formula:
`drift_level      ∈ {LOW, HIGH}          (from max PSI vs. thresholds)
evaluation_level ∈ {GOOD, BAD, UNKNOWN}  (from production accuracy vs. champion accuracy)

(LOW,  GOOD)    -> GREEN,    "Continue"
(HIGH, GOOD)    -> WARNING,  "Investigate"
(LOW,  BAD)     -> CRITICAL, "Investigate model"
(HIGH, BAD)     -> CRITICAL, "Retrain/review"   <- triggers auto-retrain
(HIGH, UNKNOWN) -> WARNING,  "Obtain ground truth" <- triggers auto-retrain
(LOW,  UNKNOWN) -> NORMAL,   "Continue monitoring"`,
    algorithm: 'The platform never retrains on drift alone — automatic retraining fires only when drift is HIGH AND evaluation is not confirmed GOOD (i.e. BAD or UNKNOWN).',
    metrics: ['overall_status, recommended_action, triggered_retrain'],
  },
]

export default function ModelsAlgosTab() {
  return (
    <div className="grid">
      <section className="card span-2">
        <h2>Formulas &amp; algorithms</h2>
        <p className="muted">Every number this platform shows you traces back to one of the formulas below.</p>
        <FlowAnimation steps={PIPELINE_STEPS} caption="Churn features -> ChurnMLP -> class-balanced loss -> quality gate" />
      </section>

      <section className="card span-2">
        <div className="formula-grid">
          {FORMULA_SECTIONS.map((section) => (
            <article key={section.id} className="formula-card card animate-in">
              <h3>{section.title}</h3>
              <pre className="code-block formula-math">{section.formula}</pre>
              <p>{section.algorithm}</p>
              {section.metrics && (
                <p className="muted"><strong>Tracked as:</strong> {section.metrics.join('; ')}</p>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

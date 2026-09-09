/** Production ML Continuous Training Platform glossary */

export const GLOSSARY_TOPICS = [
  { id: 'pipeline', label: 'Pipeline & Triggers' },
  { id: 'evaluation', label: 'Evaluation & Gates' },
  { id: 'deployment', label: 'Deployment & Rollback' },
  { id: 'monitoring', label: 'Drift & Monitoring' },
  { id: 'platform', label: 'Platform' },
]

export function glossaryTermsForTopic(topicId) {
  if (topicId === 'all') return Object.keys(GLOSSARY)
  return Object.entries(GLOSSARY)
    .filter(([, e]) => e.topic === topicId)
    .map(([id]) => id)
}

export const GLOSSARY = {
  continuous_training: {
    term: 'Continuous Training (CT)',
    topic: 'pipeline',
    definition: 'Automatically retraining a production model whenever predefined conditions occur (drift, performance dip, schedule, new data, or a manual request).',
    inThisStack: 'The whole app — app/pipeline_engine.py\'s run_pipeline() implements the closed loop end to end, triggered by Airflow or the monitoring pipeline.',
  },
  dag: {
    term: 'DAG (Directed Acyclic Graph)',
    topic: 'pipeline',
    definition: 'A workflow made of steps with dependencies but no cycles — the standard shape for a data/ML pipeline.',
    inThisStack: 'The 16-stage training DAG defined in app/pipeline_engine.py\'s DAG_STAGES, orchestrated by Airflow\'s training_pipeline DAG.',
  },
  ingestion_dag: {
    term: 'Data ingestion DAG',
    topic: 'pipeline',
    definition: 'A workflow whose only job is to fetch, store, and validate new raw data before anything downstream uses it.',
    inThisStack: 'airflow/dags/data_ingestion_dag.py — fetch_customer_data -> write_to_s3_and_validate -> publish_dataset, running daily.',
  },
  volume_anomaly: {
    term: 'Data volume anomaly',
    topic: 'pipeline',
    definition: 'The actual row count of a training dataset falls far outside the expected range — a signal that something upstream is broken, not just "less data than usual".',
    inThisStack: 'app/pipeline_engine.py\'s check_volume_anomaly stage compares actual rows to CMP_EXPECTED_VOLUME +/- 20%; a breach BLOCKS the run.',
  },
  great_expectations: {
    term: 'Great Expectations (GX)',
    topic: 'pipeline',
    definition: 'A popular Python library for declaring and checking "expectations" about data (schema, nulls, ranges, distributions).',
    inThisStack: 'Stood in for by app/ml/data_quality.py — a lightweight from-scratch implementation of the same 5 checks (schema, nulls, labels, class balance, freshness).',
  },
  feature_engineering: {
    term: 'Feature engineering',
    topic: 'pipeline',
    definition: 'Transforming raw fields into the numeric representation a model actually trains on (e.g. standardizing, encoding booleans).',
    inThisStack: 'app/data_generator.py\'s records_to_arrays() standardizes tenure/charges/age/tickets/usage and encodes the 3 boolean flags.',
  },
  champion_challenger: {
    term: 'Champion / Challenger',
    topic: 'evaluation',
    definition: 'The champion is the model version currently serving production traffic; a challenger (candidate) is a newly trained model competing to replace it.',
    inThisStack: 'ModelVersion.is_champion flags the current champion; every new candidate is compared against it in compare_champion / quality_gate.',
  },
  quality_gate_term: {
    term: 'Quality gate',
    topic: 'evaluation',
    definition: 'A mandatory set of pass/fail conditions (minimum metrics + maximum regression) a candidate model must satisfy before it can be promoted.',
    inThisStack: 'app/ml/gates.py\'s evaluation_gate() — see the Formulas & Algorithms tab for the exact math.',
  },
  regression_pct: {
    term: 'Regression percentage',
    topic: 'evaluation',
    definition: 'How much worse a candidate\'s metric is than the champion\'s, expressed as a percentage of the champion\'s value.',
    inThisStack: 'Computed in evaluation_gate(); a candidate is rejected once this exceeds CMP_MAX_REGRESSION_PCT (default 10%).',
  },
  f1_score: {
    term: 'F1 score',
    topic: 'evaluation',
    definition: 'The harmonic mean of precision and recall — a single number balancing both false positives and false negatives.',
    inThisStack: 'The primary gating metric computed by app/ml/evaluation_metrics.py\'s classification_metrics().',
  },
  class_imbalance: {
    term: 'Class imbalance',
    topic: 'evaluation',
    definition: 'A dataset where one label is far more common than another, which can make naively-trained models collapse to always predicting the majority class.',
    inThisStack: 'Seeded as the "label_imbalance" scenario — churn is forced down to ~2%, typically failing the minimum-recall floor.',
  },
  decision_threshold: {
    term: 'Decision threshold',
    topic: 'evaluation',
    definition: 'The probability cutoff above which a prediction is classified positive (churn) rather than negative (retain).',
    inThisStack: 'app/ml/pytorch_trainer.py\'s best_threshold_for_f1() tunes this on the validation split instead of assuming a naive 0.5 cutoff.',
  },
  model_registry: {
    term: 'MLflow Model Registry',
    topic: 'platform',
    definition: 'MLflow\'s catalog of named, versioned models with lifecycle stages (Staging/Production/Archived).',
    inThisStack: 'app/integrations/mlflow_utils.py\'s register_run_as_model_version() and transition_stage() — only called after the quality gate PASSes.',
  },
  canary_deployment: {
    term: 'Canary deployment',
    topic: 'deployment',
    definition: 'Rolling a new version out gradually (e.g. 5% -> 25% -> 50% -> 100% of traffic) instead of switching everyone over at once, to limit the blast radius of a bad release.',
    inThisStack: 'app/pipeline_engine.py\'s CANARY_STAGES, recorded as DeploymentEvent rows for every promotion.',
  },
  rollback: {
    term: 'Rollback',
    topic: 'deployment',
    definition: 'Reverting production traffic from the current champion back to the previously promoted (archived) version.',
    inThisStack: 'app/pipeline_engine.py\'s rollback() — a single reversible operation, not a new training run.',
  },
  kubernetes_pod_operator: {
    term: 'KubernetesPodOperator',
    topic: 'deployment',
    definition: 'An Airflow operator that runs a task as its own pod on a Kubernetes cluster (e.g. EKS), instead of on an Airflow worker.',
    inThisStack: 'Simulated here — deploy_stage/smoke_test/deploy_production stages record the same events a real EKS rollout would produce, without an actual cluster.',
  },
  drift_detection_term: {
    term: 'Drift detection',
    topic: 'monitoring',
    definition: 'Statistically comparing a model\'s current input/output distribution against its training-time distribution to catch silent data shifts.',
    inThisStack: 'app/monitoring_engine.py\'s run_monitoring_check(), using app/ml/drift.py\'s PSI and KS implementations.',
  },
  psi: {
    term: 'Population Stability Index (PSI)',
    topic: 'monitoring',
    definition: 'A single number summarizing how much a distribution has shifted between two samples, computed by binning both into the same buckets.',
    inThisStack: 'app/ml/drift.py\'s psi_numeric() — classified GREEN (<0.10), WARNING (0.10-0.25), or CRITICAL (>0.25).',
  },
  ks_test: {
    term: 'Kolmogorov-Smirnov (KS) test',
    topic: 'monitoring',
    definition: 'A statistical test comparing two distributions via the maximum distance between their cumulative distribution functions.',
    inThisStack: 'app/ml/drift.py\'s ks_test() — reported alongside PSI for every feature in a drift check.',
  },
  decision_matrix_term: {
    term: 'Drift × evaluation decision matrix',
    topic: 'monitoring',
    definition: 'A lookup table combining a drift signal (LOW/HIGH) with an evaluation signal (GOOD/BAD/UNKNOWN) into one overall status and recommended action.',
    inThisStack: 'app/ml/decision_matrix.py\'s DECISION_MATRIX — the platform\'s explicit stance that "drift alone does not indicate model failure."',
  },
  auto_retrain: {
    term: 'Drift-triggered automatic retraining',
    topic: 'monitoring',
    definition: 'Kicking off a new training run automatically once the decision matrix says drift is HIGH and quality is not confirmed GOOD.',
    inThisStack: 'app/monitoring_engine.py calls pipeline_engine.run_pipeline(trigger_type="drift", ...) directly when should_retrain() is true.',
  },
  fastapi: {
    term: 'FastAPI',
    topic: 'platform',
    definition: 'A Python web framework that auto-generates interactive API documentation (Swagger/OpenAPI) directly from your route and Pydantic type hints.',
    inThisStack: 'backend/app/main.py — every router below is documented at /docs and /redoc for free.',
  },
  prometheus_term: {
    term: 'Prometheus',
    topic: 'platform',
    definition: 'A metrics collection and alerting system that periodically "scrapes" a `/metrics` endpoint on each service it monitors.',
    inThisStack: 'app/integrations/prometheus_metrics.py exposes churn_prediction_*/churn_drift_psi_max/churn_training_runs_total counters and gauges.',
  },
  grafana_term: {
    term: 'Grafana',
    topic: 'platform',
    definition: 'A dashboarding tool that visualizes metrics from a data source such as Prometheus.',
    inThisStack: 'observability/grafana/dashboards/churn-platform.json — auto-provisioned on startup, no manual setup required.',
  },
  splunk_hec: {
    term: 'Splunk HTTP Event Collector (HEC)',
    topic: 'platform',
    definition: 'A Splunk endpoint that accepts structured JSON events over HTTP for indexing and search, without needing a forwarder agent.',
    inThisStack: 'app/integrations/splunk_utils.py\'s send_event() — best-effort delivery, never blocks the pipeline if Splunk is unreachable.',
  },
  minio_s3: {
    term: 'MinIO (S3-compatible storage)',
    topic: 'platform',
    definition: 'An open-source object store that implements the same API as Amazon S3, so code written against S3 works unmodified against it.',
    inThisStack: 'app/integrations/s3_utils.py — every dataset version is also written to a MinIO bucket via boto3.',
  },
}

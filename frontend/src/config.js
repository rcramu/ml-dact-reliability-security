const uiPort = import.meta.env.VITE_PUBLIC_UI_PORT || '3070'
const apiPort = import.meta.env.VITE_PUBLIC_API_PORT || '8170'
const pgPort = import.meta.env.VITE_PUBLIC_PG_PORT || '5480'
const pgDb = import.meta.env.VITE_PUBLIC_PG_DB || 'churn_platform'
const mlflowPort = import.meta.env.VITE_PUBLIC_MLFLOW_PORT || '5030'
const grafanaPort = import.meta.env.VITE_PUBLIC_GRAFANA_PORT || '3370'
const prometheusPort = import.meta.env.VITE_PUBLIC_PROMETHEUS_PORT || '9300'
const minioConsolePort = import.meta.env.VITE_PUBLIC_MINIO_CONSOLE_PORT || '9371'
const splunkPort = import.meta.env.VITE_PUBLIC_SPLUNK_PORT || '8370'
const airflowPort = import.meta.env.VITE_PUBLIC_AIRFLOW_PORT || '8770'

export const stackConfig = {
  uiPort, apiPort, pgPort, pgDb, mlflowPort, grafanaPort, prometheusPort, minioConsolePort, splunkPort, airflowPort,
  uiUrl: `http://localhost:${uiPort}`,
  apiUrl: `http://localhost:${apiPort}`,
  mlflowUrl: `http://localhost:${mlflowPort}`,
  grafanaUrl: `http://localhost:${grafanaPort}`,
  prometheusUrl: `http://localhost:${prometheusPort}`,
  minioConsoleUrl: `http://localhost:${minioConsolePort}`,
  splunkUrl: `http://localhost:${splunkPort}`,
  airflowUrl: `http://localhost:${airflowPort}`,
}

export const MODEL_NAME = 'customer-churn'

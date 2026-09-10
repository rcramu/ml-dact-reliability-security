# STRIDE Threat Model — kind local-EKS window (`dact-local-eks`)

Manual threat-modeling for the **kind** observation window (namespace `dact`,
host ports from `k8s/kind-config.yaml`). This remaps Section 6.3 away from
Paper A's aspirational AWS EKS/IAM diagram and away from the Compose
`cmp_*` snapshot. Credentials for this cluster live in the gitignored
`k8s/.local-secret.env` of the Paper A deposit; they are not repeated here.

| Trust boundary | STRIDE category | Finding | Severity | Evidence |
|---|---|---|---|---|
| External client → backend NodePort (`127.0.0.1:8166`) | Tampering / DoS | No authentication or rate limiting on `/api/v1/*`. Any client that can reach the mapped host port can trigger training, joint-retrain, or rollback. | High | Paper A `backend/app/main.py` mounts routers with no auth dependency; harness `POST /training` and `POST /rollback` succeed with no credentials. |
| Airflow webserver NodePort (`127.0.0.1:8766`) | Spoofing / Elevation of privilege | Airflow UI is published on the kind node. Admin password is generated into a local secret file (not the Compose `admin`/`admin` default), but the UI is still a single shared credential with cluster-wide DAG trigger rights. | High | `k8s/deploy-local-eks.sh` creates `AIRFLOW_ADMIN_PASSWORD` in `.local-secret.env`; Service `airflow-webserver` is NodePort 30076 / host 8766. |
| backend → MLflow (`http://mlflow:5000`) | Tampering | Unauthenticated HTTP write access to the tracking server and model registry from any pod in `dact`. | Medium | `k8s/backend.yaml` `CTP_MLFLOW_TRACKING_URI=http://mlflow:5000`; `mlflow_utils.py` sends no auth headers. |
| MLflow artifact PVC | Information disclosure / Tampering | Kind has **no MinIO / S3**. Artifacts sit on `mlflow-pvc` (`--default-artifact-root=/mlflow/artifacts`). Compromise of the MLflow pod is full artifact read/write; there is no per-service IAM/IRSA policy. | Medium | `k8s/mlflow.yaml`. Compose-window MinIO root-key finding does not apply here. |
| Postgres Service (NodePort 30476 / host 5476) | Information disclosure / Tampering | Database credentials are in a Kubernetes Secret (`dact-secrets`), which is the correct pattern, but the Service is still published to the host. Anyone with the secret and host access has full model/run state. | High | `k8s/postgres.yaml` `secretKeyRef`; kind `extraPortMappings` hostPort 5476. |
| `log_mlflow` / `register_model` stages | Repudiation / Tampering (silent failure) | MLflow client still swallows all exceptions ("must never break the pipeline"). A candidate can be quality-gated and promoted in Postgres while the registry write silently failed. | High (integrity) | `backend/app/integrations/mlflow_utils.py`; re-tested by the kind `mlflow_outage` scenario. |
| Rollback endpoint (`POST /rollback`) | Elevation of privilege | Unauthenticated, no approval step — one HTTP call changes the production champion. | High | `backend/app/routers/training.py`; exercised in the kind rollback trial. |

## Summary

Seven boundaries were reviewed on the **actual kind topology** (backend,
Airflow, MLflow, MLflow PVC, Postgres, silent registry write, rollback API).
**Five are High.** The Compose-specific Grafana anonymous-access and Splunk
HEC findings do **not** apply: those services are not deployed on
`dact-local-eks`. Kubernetes Secrets replace Compose hardcoded DB passwords,
which is an improvement, but NodePort publication plus an unauthenticated
training/rollback API remain the dominant risks.

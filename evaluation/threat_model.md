# STRIDE Threat Model — cmp_ Reference Stack

Manual threat-modeling analysis (Paper B, Section 6.3), applied to the trust
boundaries in Paper A's Figure 1 (CI/Pipeline → Airflow, Airflow → MLflow,
Worker Pods → S3, ALB → EKS) as actually implemented by this Docker Compose
reference stack. Findings are grounded in the real files in this repo
(`docker-compose.yml`, `backend/app/config.py`, `backend/app/integrations/`),
cross-referenced against the automated findings in
`evaluation/results/security_scan.json`.

| Trust boundary | STRIDE category | Finding | Severity | Evidence |
|---|---|---|---|---|
| External client → `cmp_backend` (port 8170) | Tampering / DoS | No authentication or rate limiting on any `/api/v1/*` route — any client reachable on the port can trigger training, rollback, or drift checks. | High | `backend/app/main.py` mounts all routers with no auth dependency; confirmed by successfully calling `POST /training` and `POST /rollback` with no credentials during the fault-injection harness (Section 6.2). |
| Airflow webserver (port 8770) | Spoofing / Elevation of privilege | Airflow web UI reachable with the seeded `admin`/`admin` credential created at container-init time; no secrets-manager-issued credential. | High | `docker-compose.yml` `airflow-init` command: `airflow users create --username admin --password admin ...`. |
| `cmp_backend` → `cmp_mlflow` | Tampering | The MLflow client has unauthenticated, unencrypted HTTP write access to the tracking server and model registry (`CMP_MLFLOW_TRACKING_URI: http://mlflow:5000`); any container on the compose network can register/transition model versions. | Medium | `docker-compose.yml` backend env; `backend/app/integrations/mlflow_utils.py` has no auth headers. |
| `cmp_backend` → `cmp_minio` (S3-compatible) | Information disclosure / Tampering | Static root credentials (`cmp_minio` / `cmp_minio_secret`) hardcoded in compose and `config.py`; no per-service scoped IAM policy (unlike the AWS IRSA design in Paper A §10.2) — any compromised container with these env vars has full bucket read/write. | Medium | `backend/app/config.py` `s3_access_key`/`s3_secret_key` defaults; confirmed present in plaintext in `docker-compose.yml`/`.env`. |
| Grafana (port 3370) | Spoofing / Information disclosure | `GF_AUTH_ANONYMOUS_ENABLED: "true"` grants unauthenticated Viewer access to all dashboards (production metrics, pipeline SLA data); admin password left at the documented default. | High | `docker-compose.yml` grafana service env; confirmed by `evaluation/security_scan.py`'s credential-hygiene check. |
| Splunk HEC (port 8371) | Tampering | `SPLUNK_HEC_TOKEN` hardcoded as a static, low-entropy-looking value (`22222222-...`) in compose; any party with network access to the port can inject arbitrary log events into the audit/observability pipeline. | Medium | `docker-compose.yml` splunk service env; `backend/app/integrations/splunk_utils.py` sends events using this token with `SPLUNK_VERIFY_TLS=false`, so the channel is also unauthenticated-TLS. |
| `write_to_s3` / `log_mlflow` pipeline stages | Repudiation / Tampering (silent failure) | Both stages catch **all** exceptions and continue the pipeline ("S3/MLflow must never block training" — by design for reliability, but with a security/integrity side effect): a model can be promoted to production while its MLflow registry entry silently never existed, with no alert distinguishing this from a normal run. | High (integrity) | `backend/app/pipeline_engine.py` stages `write_to_s3`/`log_mlflow`/`register_model`; **empirically confirmed** by the `mlflow_outage` fault-injection scenario (Section 6.2) — see `evaluation/results/fault_injection.json` `integrity_findings_count`. |
| Rollback endpoint (`POST /rollback`) | Elevation of privilege | No authentication and no confirmation/approval step — a single unauthenticated request permanently changes which model version serves production traffic. | High | `backend/app/routers/training.py` `trigger_rollback`; exercised directly in Section 6.2's `rollback_mechanism` scenario. |

## Summary

Of 7 trust boundaries reviewed, **5 are rated High severity**, driven by a
consistent pattern across this reference stack: every internal
service-to-service and operator-to-API boundary relies on network isolation
alone (Docker Compose's private network) with no authentication layer, and
several components ship with hardcoded or default credentials intended for
local development. This is consistent with the stack's stated purpose as a
teaching/demo reference implementation rather than a hardened production
deployment, but it is a materially different security posture than the
IAM/IRSA + Kubernetes RBAC design described in Paper A, Section 10.2 — that
design was never implemented or tested here, only diagrammed. The most
security-relevant *functional* finding (silent MLflow-registration failure
during promotion) was discovered empirically through fault injection, not
through this manual review — a concrete example of why Paper B's protocol
combines both methods rather than relying on either alone.

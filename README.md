# Reliability and security evaluation of a closed-loop MLOps stack

Public deposit for the companion JSS manuscript:

**Reliability and Security Evaluation of a Closed-Loop MLOps System: A Comparative Study Against Manual and Scheduled Retraining**

This repository is the archived Docker Compose snapshot of the system under test plus the evaluation harness that produced Tables 1–3 and Figures 4–8. It is the empirical companion to [ml-dact](https://github.com/rcramu/ml-dact) / JSS manuscript **JSSOFTWARE-D-26-02282** (*Quality-Gated Continuous Training under Drift: An Observational Case Study of an Inspectable MLOps Architecture*).

How to regenerate results: [`EVALUATION.md`](EVALUATION.md).

## What is in this repository

| Path | Role |
| --- | --- |
| `backend/`, `airflow/`, `frontend/`, `db/`, `observability/`, `docker-compose.yml` | Archived Compose snapshot (`cmp_` containers; model `customer-churn`) |
| `evaluation/` | Fault injection, security scan, STRIDE notes, maintainability metrics, A/B/C comparison, onboarding trial, figure scripts, captured JSON |
| `figures/` | Generated PNGs used in the paper |
| `.env.example` | Non-secret timing overrides only |

This is **not** an Amazon EKS or kind deployment. Paper A's kind-seed measurements live in [ml-dact](https://github.com/rcramu/ml-dact). Treat the two repositories as two observation windows on the same architecture family.

## Quick start (Docker Compose)

```bash
git clone https://github.com/rcramu/ml-dact-reliability-security.git
cd ml-dact-reliability-security
cp .env.example .env
docker compose up --build
```

The stack is a local demo. Service URLs (frontend `:3070`, API `:8170`, MLflow `:5030`, Airflow `:8770`, and the rest) are listed in `docker-compose.yml`. Copy `.env.example` to `.env` only to override timing constants. Do not treat compose defaults as production credentials — they are the hygiene findings reported in the paper (Table 2).

On first boot the backend seeds `customer-churn`, runs the demo training/monitoring walk, and starts live traffic generation so Prometheus/Grafana keep moving.

Airflow DAGs are created paused. Open the Airflow UI, unpause them, and trigger a run (or wait for the schedule) to call the same backend endpoints as the UI.

```bash
docker compose down          # keep volumes
docker compose down -v       # delete volumes (fresh reseed on next up)
```

## Evaluation harness

Static analyses (`maintainability_metrics.py`, dependency/`npm audit` parts of `security_scan.py`) and figure regeneration (`make_figures.py`, `make_cascade_figure.py`, `make_stride_figure.py`) need no running containers.

Live scripts (`fault_injection.py`, `approach_comparison.py`, `onboarding_trial.py`, and `docker scout` in `security_scan.py`) target container names `cmp_backend`, `cmp_mlflow`, `cmp_minio` and ports `8170` / `5030` / `9370`. Bring this folder up with `docker compose up -d --build`, then see [`EVALUATION.md`](EVALUATION.md).

```bash
python3 -m venv evaluation/.venv
evaluation/.venv/bin/pip install -r evaluation/requirements.txt
```

## Security notice

`docker-compose.yml` contains **demo-only** service passwords and a placeholder HEC token. They exist so the archived snapshot matches the hygiene review in the paper. They are not production secrets, API keys, or cloud credentials. Do not reuse them outside this local stack. A copied `.env` is gitignored.

## License / reuse

Released to support review and reproduction of the companion manuscript. Synthetic records only; no personal data.

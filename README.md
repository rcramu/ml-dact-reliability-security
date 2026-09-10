# Reliability and security evaluation of a closed-loop MLOps stack

Public deposit for the companion JSS manuscript:

**An Empirical Reliability and Security Evaluation of Drift-Aware Continuous Training**

This repository is the archived Docker Compose snapshot plus the evaluation harness (`--runtime k8s|compose`) that produced Tables 1–3. The **primary** measurement window is Paper A's kind cluster (`dact-local-eks`, context `kind-dact-local-eks` only; model `churn-predictor`). Compose (`cmp_*`, `customer-churn`) is the archived second window. Companion: [ml-dact](https://github.com/rcramu/ml-dact) / **JSSOFTWARE-D-26-02282**.

How to regenerate results: [`docs/eval.md`](docs/eval.md).

## What is in this repository

| Path | Role |
| --- | --- |
| `backend/`, `airflow/`, `frontend/`, `db/`, `observability/`, `docker-compose.yml` | Archived Compose snapshot (`cmp_` containers; model `customer-churn`) |
| `docs/` | Case notes; [`docs/eval.md`](docs/eval.md) is how to regenerate Tables 1–3 |
| `evaluation/` | Harness scripts (`--runtime k8s\|compose`) |
| `evaluation/results/` | **Data folder** — captured JSON for Tables 1–3 (see `evaluation/results/README.md`) |
| `figures/` | Generated PNGs used in the paper |
| `.env.example` | Non-secret timing overrides only |

Kind deploy lives in [ml-dact](https://github.com/rcramu/ml-dact) `code/k8s/`. This repo's harness talks to that cluster only via `--context kind-dact-local-eks` (`evaluation/k8s_runtime.py`). Never use the default kubecontext.

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

Live scripts accept `--runtime k8s` (kind, port 8166) or `--runtime compose` (`cmp_*`, port 8170). See [`docs/eval.md`](docs/eval.md).

```bash
python3 -m venv evaluation/.venv
evaluation/.venv/bin/pip install -r evaluation/requirements.txt
```

## Security notice

`docker-compose.yml` contains **demo-only** service passwords and a placeholder HEC token. They exist so the archived snapshot matches the hygiene review in the paper. They are not production secrets, API keys, or cloud credentials. Do not reuse them outside this local stack. A copied `.env` is gitignored.

## License / reuse

Released to support review and reproduction of the companion manuscript. Synthetic records only; no personal data.

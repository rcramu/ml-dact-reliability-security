# Evaluation harness

Companion deposit for **An Empirical Reliability and Security Evaluation of Drift-Aware Continuous Training**.

**Data folder:** [`evaluation/results/`](../evaluation/results/) holds every captured JSON file used in Tables 1–3. See [`evaluation/results/README.md`](../evaluation/results/README.md).

Two observation windows, selected with `--runtime`:

| Flag | Cluster / stack | Backend | Model | Writes |
|---|---|---|---|---|
| `--runtime k8s` (primary) | kind `dact-local-eks`, context **`kind-dact-local-eks` only** | `http://127.0.0.1:8166` | `churn-predictor` | `*_kind.json` |
| `--runtime compose` | archived `docker compose` (`cmp_*`) | `http://localhost:8170` | `customer-churn` | original JSON names |

**Never run bare `kubectl`.** This machine may have a production EKS context. Every kubectl call in `evaluation/k8s_runtime.py` passes `--context kind-dact-local-eks`.

## Kind (local EKS)

Bring up Paper A's cluster (from that deposit, not this one):

```bash
# Paper A: A.ML-drift-aware-continuous-training/code/k8s/deploy-local-eks.sh
# Cluster name dact-local-eks; host ports 3066 / 8166 / 5026 / 8766 / 5476
```

Then from this repository:

```bash
python3 -m venv evaluation/.venv
evaluation/.venv/bin/pip install -r evaluation/requirements.txt
evaluation/.venv/bin/python evaluation/fault_injection.py --runtime k8s --trials 5
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --profile stable
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --profile drifted
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --profile severe_drift
evaluation/.venv/bin/python evaluation/onboarding_trial.py --runtime k8s
evaluation/.venv/bin/python evaluation/f1_only_ablation.py
```

Kind A/B/C maps profiles to generator scenarios: `stable`→`healthy`, `drifted`→`feature_drift`, `severe_drift`→`regression`. Approach C is `POST /joint-retrain`. There is no MinIO on kind.

Published Table 3 files (`approach_comparison_{profile}_kind.json`) are not overwritten unless you pass `--overwrite-published`. For an n≥3 replica on a **dedicated** model (so `churn-predictor`'s champion does not walk):

```bash
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --model paper-b-abc --profile drifted --repeats 3
```

Create the dedicated model first (`evaluation/ensure_kind_model.py --model paper-b-abc`); there is no POST /models route. That writes `approach_comparison_{profile}_kind_repeats.json`. Kind idle-in-transaction observe-only: `evaluation/orphan_observe.py --trials 5` → `orphan_kind.json` (does not overwrite Table 1). Every kubectl call stays on `--context kind-dact-local-eks`.

## Compose (archived snapshot)

```bash
docker compose up -d --build
evaluation/.venv/bin/python evaluation/fault_injection.py --runtime compose --trials 5
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime compose --profile severe_drift
```

Do not overwrite `evaluation/results/fault_injection.json` or `approach_comparison_{profile}.json` if you are also keeping the published Compose window.

## Other scripts

`security_scan.py` and `maintainability_metrics.py` are static. Linux `pip-audit --disable-pip --no-deps` on `backend/requirements.txt` (image `python:3.11-bookworm`) writes `evaluation/results/pip_audit_linux.json`. `make_figures.py` reads `evaluation/results/`. STRIDE for kind is `evaluation/threat_model_kind.md`.

## Known limitations

Code churn is a short-window measurement over this deposit's git history (`maintainability_metrics.json`): SUT modules are archive-commit additions only; later churn is concentrated in `evaluation/`. Kind A/B/C cells are n=1 per scenario. Kind backend self-heal is measured against a 30 s `/ready` bound, not “the Deployment eventually created a pod.” Host `pip-audit` cannot build `scipy`/`psycopg2-binary`; the Linux `--no-deps` run still does not resolve transitives.

# Evaluation harness

Companion deposit for **Reliability and Security Evaluation of a Closed-Loop MLOps System**. Independent of any workshop path. Clone this repository and work from its root.

```
.
  backend/, airflow/, frontend/, db/, docker-compose.yml, .env.example
      Archived snapshot of the system under test. Bring it up with
      `docker compose up -d --build` from this directory. Container prefix
      is `cmp_`. A fresh compose project will not share state with any
      other local demo.
  evaluation/
    fault_injection.py         Section 6.2 reliability / chaos harness
    security_scan.py           Section 6.3 dependency / container / credential scan
    threat_model.md            Section 6.3 manual STRIDE analysis
    maintainability_metrics.py Section 6.4 complexity / LOC
    approach_comparison.py     Section 6.1 / 9 A/B/C (`--profile stable|drifted|severe_drift`)
    onboarding_trial.py        Section 6.4 / 8 add + tear down a second model
    make_figures.py            writes figures/*.png from results/ JSON
    make_cascade_figure.py     Figure 8: orphaned-transaction cascade
    make_stride_figure.py      Figure 5: STRIDE severity map
    results/                   captured JSON used in the paper
    requirements.txt           radon, requests, matplotlib
  figures/
    figure1_reliability_mttr.png
    figure2_abc_comparison.png
    figure3_orphaned_transaction_cascade.png
    figure4_stride_severity.png
```

## Running against a live stack

`fault_injection.py` and the dynamic checks in `security_scan.py` (`docker scout`) target a **running** instance by container name (`cmp_backend`, `cmp_mlflow`, `cmp_minio`) and port (`localhost:8170` / `5030` / `9370`).

```bash
docker compose up -d --build
```

If you remap ports or container names, edit the `BACKEND` / `MLFLOW` / `MINIO` constants at the top of `fault_injection.py`.

`approach_comparison.py` and `onboarding_trial.py` use the same `BACKEND` constant. `onboarding_trial.py` temporarily adds `customer-churn-eu` via `docker exec` into `cmp_backend`, then tears it down in the same run. It is safe to rerun; if interrupted, `customer-churn-eu` may remain in `GET /api/v1/models` until cleaned up (see the script's `CLEANUP_SNIPPET`).

`maintainability_metrics.py` and the dependency / `npm audit` parts of `security_scan.py` are static. `make_figures.py` only reads `evaluation/results/` and needs no containers.

```bash
python3 -m venv evaluation/.venv
evaluation/.venv/bin/pip install -r evaluation/requirements.txt
evaluation/.venv/bin/python evaluation/make_figures.py
```

## Known limitations

Code churn (paper ref. [14]) was unavailable at measurement time because the snapshot had no VCS history. After this repository is initialized that limitation is historical: the paper still reports churn as not executed.

`security_scan.py` queries the OSV.dev API for each pinned package in `backend/requirements.txt` rather than using the `pip-audit` CLI. Local `pip-audit` resolution failed on the development machine (missing `gfortran` / `pg_config` needed to build `scipy` / `psycopg2-binary` from source). The vulnerability database is the same, but only the 18 directly pinned top-level packages are covered, not transitive dependencies.

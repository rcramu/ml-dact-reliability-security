# Case: A/B/C n≥3

Table 3 is n=1 per cell. `feature_drift` promoted three times on `churn-predictor`, so later rows do not share one champion.

Use a **dedicated** model. Do not overwrite published `approach_comparison_*_kind.json`.

```bash
# cluster must already be up (Paper A deploy-local-eks.sh)
# every kubectl call: --context kind-dact-local-eks only
evaluation/.venv/bin/python evaluation/ensure_kind_model.py --model paper-b-abc
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --model paper-b-abc --profile stable --repeats 3
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --model paper-b-abc --profile drifted --repeats 3
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --model paper-b-abc --profile severe_drift --repeats 3
```

Writes `evaluation/results/approach_comparison_{profile}_kind_repeats.json`. Report median detection/recovery and how often C fires or holds. Do not overwrite published `approach_comparison_*_kind.json`.

Captured 2026-09-10: C live-fired **0/9** cells (SIGNIFICANT×GOOD on `feature_drift`). Champion walked only after the first drifted trial's supplementary C+B promotions. Flagship `churn-predictor` stayed v21.

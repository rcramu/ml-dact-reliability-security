# Case: A/B/C n≥3

Table 3 is n=1 per cell. `feature_drift` promoted three times on `churn-predictor`, so later rows do not share one champion.

Use a **dedicated** model. Do not overwrite published `approach_comparison_*_kind.json`.

```bash
# cluster must already be up (Paper A deploy-local-eks.sh)
# every kubectl call: --context kind-dact-local-eks only
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --model paper-b-abc --profile stable --repeats 3
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --model paper-b-abc --profile drifted --repeats 3
evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --model paper-b-abc --profile severe_drift --repeats 3
```

Writes `evaluation/results/approach_comparison_{profile}_kind_repeats.json`. Report median detection/recovery and how often C fires or holds. Kind is down until Docker is back.

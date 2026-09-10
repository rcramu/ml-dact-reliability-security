# Data folder

This directory is the **captured-data folder** for the paper. Every numeric cell in Tables 1–3 is taken from these JSON files. The harness writes here; `make_figures.py` and `f1_only_ablation.py` only read from here.

| File | Window | Paper use |
|---|---|---|
| `fault_injection_kind.json` | kind | Table 1 (primary) |
| `approach_comparison_{stable,drifted,severe_drift}_kind.json` | kind | Table 3 (primary) |
| `onboarding_trial_kind.json` | kind | Section 8 onboarding |
| `kind_environment.json` | kind | Section 7 environment box |
| `fault_injection.json` | Compose | Table 1 (secondary window) |
| `approach_comparison_{stable,drifted,severe_drift}.json` | Compose | Table 3b |
| `onboarding_trial.json` | Compose | Section 8 onboarding |
| `f1_only_ablation.json` | both (recount only) | Section 7 / 9 F1-only ablation |
| `security_scan.json` | Compose pins / OSV | Table 2 (86 OSV IDs) |
| `pip_audit_linux.json` | Linux `pip-audit --no-deps` | Table 2 (58 rows / 52 unique IDs) |
| `maintainability_metrics.json` | static source tree + deposit git | Section 8 complexity/LOC and short-window churn |
| `approach_comparison_{stable,drifted,severe_drift}_kind_repeats.json` | kind | n≥3 A/B/C replica on `paper-b-abc` (not Table 3 source) |
| `orphan_kind.json` | kind | idle-in-transaction counts around backend-pod kills (Figure 8 is still Compose-only) |

Re-running `--runtime k8s` overwrites `*_kind.json` only. Re-running `--runtime compose` overwrites the original names — keep a copy if you still need the published Compose window.

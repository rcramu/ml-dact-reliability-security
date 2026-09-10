# Case: kind idle-in-transaction check

Figure 8 is Compose-only. After kind backend-pod kills, Table 1 reported no orphaned `RUNNING` pipeline row. This case asks whether Postgres `idle in transaction` still accumulates (the Compose cascade).

Observe only, via `evaluation/k8s_runtime.py` (`kubectl --context kind-dact-local-eks exec deploy/postgres`):

```sql
SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction';
```

```bash
evaluation/.venv/bin/python evaluation/orphan_observe.py --trials 5
```

Writes `evaluation/results/orphan_kind.json`. Does not overwrite Table 1 (`fault_injection_kind.json`). Do not use the default kubecontext.

Captured 2026-09-10: `idle in transaction` stayed **0** before, after each of five backend-pod kills, and at the end. Companion `/ready` times in that window were 11.1–14.3 s; they do not replace Table 1.

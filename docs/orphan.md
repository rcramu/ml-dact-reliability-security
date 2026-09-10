# Case: kind idle-in-transaction check

Figure 8 is Compose-only. After kind backend-pod kills, Table 1 reported no orphaned `RUNNING` pipeline row. This case asks whether Postgres `idle in transaction` still accumulates (the Compose cascade).

Observe only, via `evaluation/k8s_runtime.py` (`kubectl --context kind-dact-local-eks exec deploy/postgres`):

```sql
SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction';
```

Run once before `fault_injection.py --runtime k8s` backend-kill trials, once after each trial, once at the end. Write counts to `evaluation/results/orphan_kind.json` when the cluster is up. Do not use the default kubecontext.

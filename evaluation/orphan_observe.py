#!/usr/bin/env python3
"""Observe-only kind idle-in-transaction check (docs/orphan.md).

Counts Postgres sessions in 'idle in transaction' before backend-pod-kill
trials, after each trial, and at the end. Does not overwrite
fault_injection_kind.json (Table 1).

Every kubectl call is pinned to kind-dact-local-eks via k8s_runtime.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from fault_injection import Stack, scenario_backend_kill_inflight
from k8s_runtime import assert_kind_context, psql

RESULTS = Path(__file__).parent / "results"

IDLE_SQL = """
SELECT count(*) FROM pg_stat_activity
WHERE state = 'idle in transaction';
"""
STATE_SQL = """
SELECT coalesce(state, 'null'), count(*)
FROM pg_stat_activity
GROUP BY state
ORDER BY 1;
"""


def _parse_count(stdout: str) -> int | None:
    nums = [int(x) for x in re.findall(r"(?m)^\s*(\d+)\s*$", stdout or "")]
    return nums[0] if nums else None


def _parse_states(stdout: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in (stdout or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].isdigit():
            out[" ".join(parts[:-1])] = int(parts[-1])
    return out


def observe(label: str) -> dict:
    idle = psql(IDLE_SQL)
    states = psql(STATE_SQL)
    return {
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(),
        "idle_in_transaction": _parse_count(idle.stdout),
        "psql_idle_returncode": idle.returncode,
        "psql_idle_stderr": (idle.stderr or "").strip() or None,
        "session_states": _parse_states(states.stdout),
        "raw_idle_stdout": (idle.stdout or "").strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()

    assert_kind_context()
    stack = Stack("k8s")
    assert stack.backend_ready(), "kind backend is not ready"

    observations = [observe("before")]
    trial_summaries = []
    for i in range(args.trials):
        one = scenario_backend_kill_inflight(stack, 1)
        trial_summaries.append(one)
        observations.append(observe(f"after_trial_{i + 1}"))
        if not requests.get(f"{stack.backend}/ready", timeout=8).json().get("ready"):
            stack.restore_backend_manual()

    observations.append(observe("end"))
    idle_counts = [o.get("idle_in_transaction") for o in observations]
    numeric = [c for c in idle_counts if isinstance(c, int)]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": "k8s",
        "kind_context": "kind-dact-local-eks",
        "protocol": (
            "Observe-only. SELECT count(*) FROM pg_stat_activity "
            "WHERE state = 'idle in transaction' via k8s_runtime.psql "
            "(kubectl --context kind-dact-local-eks exec deploy/postgres). "
            "Backend-kill trials are companion observations; Table 1 file is not overwritten."
        ),
        "trials": args.trials,
        "observations": observations,
        "idle_in_transaction_series": idle_counts,
        "idle_in_transaction_max": max(numeric) if numeric else None,
        "idle_accumulated": (
            numeric[-1] > numeric[0] if len(numeric) >= 2 else None
        ),
        "companion_backend_kill_summaries": trial_summaries,
        "table1_file_untouched": "fault_injection_kind.json",
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / "orphan_kind.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out}")
    print(json.dumps({k: report[k] for k in (
        "idle_in_transaction_series",
        "idle_in_transaction_max",
        "idle_accumulated",
        "table1_file_untouched",
    )}, indent=2))


if __name__ == "__main__":
    main()

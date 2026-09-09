#!/usr/bin/env python3
"""Approach A/B/C instrumented comparison (Paper B, Section 6.1 / Table 3).

Runs against the LIVE stack (same one fault_injection.py targets). All three
approaches use the SAME underlying 16-stage training pipeline
(`POST /training`) and the SAME `scenario="feature_drift"` synthetic-data
generator, so the pipeline logic and quality gate are held constant across
approaches — the only thing that differs is *how* retraining gets triggered:

  A — Manual:      a simulated operator polls the monitoring endpoint on a
                    short, explicitly-labeled compressed interval, waits for a
                    fixed decision-latency once drift is noticed, then
                    manually calls POST /training (trigger_type="manual").
  B — Scheduled:    calls POST /training with trigger_type="schedule" directly
                    (the same call the real weekly Airflow DAG makes) with NO
                    drift check at all — detection time is NOT measured live,
                    it is reported analytically from the DAG's configured
                    weekly cron (`0 2 * * 0`).
  C — Closed-loop:  calls POST /monitoring/check with auto_retrain=True (the
                    same call the real 30-minute monitoring DAG makes) and
                    reports whether it actually triggered retraining live.

The monitoring `profile` (stable | drifted | severe_drift, matching Paper A
Section 7.1's 3 production distributions) is parameterized via --profile and
used for Approach A/C's drift-detection step; the training `scenario` stays
fixed at "feature_drift" for all triggered retrains regardless of profile
(matching monitoring_engine.py's own auto-retrain behavior, which always uses
scenario="feature_drift" once should_retrain() fires, independent of which
profile triggered it).

Both `POST /training` and `POST /monitoring/check` run the entire pipeline
SYNCHRONOUSLY server-side (confirmed via source read of pipeline_engine.py /
monitoring_engine.py) — so a single timed HTTP call gives the true end-to-end
recovery time with no polling needed.

Usage:
    evaluation/.venv/bin/python evaluation/approach_comparison.py --profile stable
    evaluation/.venv/bin/python evaluation/approach_comparison.py --profile drifted
    evaluation/.venv/bin/python evaluation/approach_comparison.py --profile severe_drift
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BACKEND = "http://localhost:8170"
MODEL = "customer-churn"
RESULTS_DIR = Path(__file__).parent / "results"

# Simulated-operator parameters for Approach A — explicitly a compressed proxy
# for a real operator's check cadence (e.g. hourly/daily dashboard glances),
# not an empirically observed human interval. Documented, not hidden.
OPERATOR_POLL_INTERVAL_S = 5.0
OPERATOR_POLL_MAX_S = 60.0
OPERATOR_DECISION_LATENCY_S = 8.0  # simulated "notice -> decide -> click retrain"

# Analytical (not live-measured) detection-time bounds, from the actual DAG
# schedules in code/airflow/dags/*.py.
SCHEDULED_DAG_CRON = "0 2 * * 0"  # weekly, training_pipeline_dag.py
SCHEDULED_DETECTION_AVG_S = 3.5 * 86400
SCHEDULED_DETECTION_MAX_S = 7 * 86400
CLOSEDLOOP_DAG_CRON = "*/30 * * * *"  # every 30 min, monitoring_pipeline_dag.py
CLOSEDLOOP_DETECTION_AVG_S = 15 * 60
CLOSEDLOOP_DETECTION_MAX_S = 30 * 60


def _current_champion() -> dict:
    versions = requests.get(f"{BACKEND}/api/v1/models/{MODEL}/versions", timeout=10).json()
    return next(v for v in versions if v["is_champion"])


def _trigger_training(trigger_type: str, scenario: str = "feature_drift", timeout: float = 120.0):
    return requests.post(
        f"{BACKEND}/api/v1/models/{MODEL}/training",
        json={"trigger_type": trigger_type, "scenario": scenario,
              "trigger_detail": f"Paper B Table 4 A/B/C comparison ({trigger_type})"},
        timeout=timeout,
    )


def _outcome_summary(pre_champion: dict, run_payload: dict) -> dict:
    outcome = run_payload.get("outcome")
    candidate_f1 = None
    gate_reasons = None
    regression_pct = None
    for stage in run_payload.get("stages", []):
        if stage["stage_name"] == "evaluate_model":
            candidate_f1 = (stage.get("detail") or {}).get("test_f1")
        if stage["stage_name"] == "quality_gate":
            detail = stage.get("detail") or {}
            gate_reasons = detail.get("reasons")
            regression_pct = detail.get("regression_pct")
    if outcome == "PROMOTED":
        quality_f1 = candidate_f1
        promoted = True
    else:
        quality_f1 = pre_champion.get("test_f1")  # gate rejected candidate -> champion unchanged
        promoted = False
    return {
        "pipeline_status": run_payload.get("status"),
        "pipeline_outcome": outcome,
        "candidate_test_f1": candidate_f1,
        "production_f1_after": quality_f1,
        "promoted": promoted,
        "gate_reasons": gate_reasons,
        "gate_regression_pct": regression_pct,
    }


def run_approach_c(profile: str) -> dict:
    """Closed-loop: POST /monitoring/check(auto_retrain=True)."""
    pre = _current_champion()
    t0 = time.monotonic()
    resp = requests.post(
        f"{BACKEND}/api/v1/models/{MODEL}/monitoring/check",
        json={"profile": profile, "auto_retrain": True},
        timeout=60,
    )
    elapsed = round(time.monotonic() - t0, 3)
    check = resp.json()
    result = {
        "approach": "C - Closed-loop",
        "detection_time_seconds_measured": 0.0,  # the check call itself IS the detection, no separate wait
        "detection_time_note": (
            f"Live check-call latency measured at {elapsed}s. In production this check runs on a "
            f"{CLOSEDLOOP_DAG_CRON} schedule (monitoring_pipeline_dag.py), so real-world drift-onset-to-check "
            f"latency averages {CLOSEDLOOP_DETECTION_AVG_S/60:.0f} min (max {CLOSEDLOOP_DETECTION_MAX_S/60:.0f} min) — analytical, not measured here."
        ),
        "drift_level": check.get("drift_level"),
        "evaluation_level": check.get("evaluation_level"),
        "overall_status": check.get("overall_status"),
        "triggered_retrain_live": check.get("triggered_retrain"),
        "total_call_latency_seconds": elapsed,
        "operational_human_actions": 0,
    }
    if check.get("triggered_retrain"):
        run_id = check["retrain_run_id"]
        run_payload = requests.get(f"{BACKEND}/api/v1/models/{MODEL}/training/{run_id}", timeout=30).json()
        result["recovery_time_seconds"] = elapsed  # same call already included the full retrain
        result.update(_outcome_summary(pre, run_payload))
    else:
        result["recovery_time_seconds"] = None
        result["note"] = (
            "Auto-retrain did NOT fire on this live check (should_retrain()==False for the observed "
            "drift_level/evaluation_level combination) — consistent with Paper A/B's earlier observed "
            "limitation that severe_drift does not reliably yield evaluation_level=BAD against the "
            "current champion. Supplementary measurement below force-triggers the same "
            "trigger_type='drift' pipeline directly so the recovery-time component can still be reported."
        )
        t1 = time.monotonic()
        forced = _trigger_training(trigger_type="drift").json()
        forced_elapsed = round(time.monotonic() - t1, 3)
        result["supplementary_forced_recovery_time_seconds"] = forced_elapsed
        result["supplementary_forced_outcome"] = _outcome_summary(pre, forced)
    return result


def run_approach_b() -> dict:
    """Scheduled: POST /training(trigger_type=schedule), no drift awareness."""
    pre = _current_champion()
    t0 = time.monotonic()
    run_payload = _trigger_training(trigger_type="schedule").json()
    elapsed = round(time.monotonic() - t0, 3)
    result = {
        "approach": "B - Scheduled (weekly)",
        "detection_time_seconds_measured": None,
        "detection_time_note": (
            f"Not applicable/not live-measured: Approach B retrains on a fixed {SCHEDULED_DAG_CRON} cron "
            f"(training_pipeline_dag.py) regardless of drift state, so 'detection' is really 'wait for next "
            f"scheduled slot' — average {SCHEDULED_DETECTION_AVG_S/86400:.1f} days, max {SCHEDULED_DETECTION_MAX_S/86400:.0f} days. Analytical, not measured here."
        ),
        "recovery_time_seconds": elapsed,
        "operational_human_actions": 0,
    }
    result.update(_outcome_summary(pre, run_payload))
    return result


def run_approach_a(profile: str) -> dict:
    """Manual: simulated operator polling loop + fixed decision latency + manual trigger."""
    pre = _current_champion()
    t0 = time.monotonic()
    polls = 0
    noticed_status = None
    while time.monotonic() - t0 < OPERATOR_POLL_MAX_S:
        polls += 1
        check = requests.post(
            f"{BACKEND}/api/v1/models/{MODEL}/monitoring/check",
            json={"profile": profile, "auto_retrain": False},
            timeout=30,
        ).json()
        if check.get("overall_status") in ("WARNING", "CRITICAL"):
            noticed_status = check["overall_status"]
            break
        time.sleep(OPERATOR_POLL_INTERVAL_S)
    detection_polling_time = round(time.monotonic() - t0, 3)
    time.sleep(OPERATOR_DECISION_LATENCY_S)
    detection_time_total = round(detection_polling_time + OPERATOR_DECISION_LATENCY_S, 3)

    t1 = time.monotonic()
    run_payload = _trigger_training(trigger_type="manual").json()
    recovery_time = round(time.monotonic() - t1, 3)

    result = {
        "approach": "A - Manual",
        "polls_before_notice": polls,
        "noticed_status": noticed_status,
        "detection_polling_time_seconds_measured": detection_polling_time,
        "simulated_decision_latency_seconds": OPERATOR_DECISION_LATENCY_S,
        "detection_time_seconds_measured": detection_time_total,
        "detection_time_note": (
            f"Polling interval ({OPERATOR_POLL_INTERVAL_S}s) and decision latency ({OPERATOR_DECISION_LATENCY_S}s) "
            "are explicitly compressed, documented proxies for a real operator's check cadence/response time, "
            "not empirically observed human behavior — the polling loop and pipeline execution themselves are real."
        ),
        "recovery_time_seconds": recovery_time,
        "operational_human_actions": 2,  # notice + manually trigger
    }
    result.update(_outcome_summary(pre, run_payload))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="severe_drift", choices=["stable", "drifted", "severe_drift"])
    args = parser.parse_args()

    assert requests.get(f"{BACKEND}/ready", timeout=5).json().get("ready"), "backend not ready"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "methodology_note": (
            "All three approaches use the same 16-stage training pipeline and the same "
            "scenario='feature_drift' data generator (different run_id -> different sampled "
            "instance of the same drift distribution per approach, not byte-identical data — "
            "see Section 6.1/9 limitations). Monitoring profile for this run: "
            f"'{args.profile}'."
        ),
        "approach_c": run_approach_c(args.profile),
        "approach_b": run_approach_b(),
        "approach_a": run_approach_a(args.profile),
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"approach_comparison_{args.profile}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out_path}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

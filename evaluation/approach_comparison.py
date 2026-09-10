#!/usr/bin/env python3
"""Approach A/B/C instrumented comparison (Paper B, Section 6.1 / Table 3).

``--runtime compose`` (default) uses the archived snapshot:
  BACKEND=http://localhost:8170, MODEL=customer-churn,
  POST /monitoring/check with profiles stable|drifted|severe_drift.
  Writes results/approach_comparison_{profile}.json

``--runtime k8s`` uses Paper A's kind cluster (context kind-dact-local-eks only):
  BACKEND=http://127.0.0.1:8166, MODEL=churn-predictor,
  GET /joint-cell and POST /joint-retrain with generator scenarios.
  Profile mapping: stable→healthy, drifted→feature_drift, severe_drift→regression.
  Writes results/approach_comparison_{profile}_kind.json

Usage:
    evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime compose --profile severe_drift
    evaluation/.venv/bin/python evaluation/approach_comparison.py --runtime k8s --profile severe_drift
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RESULTS_DIR = Path(__file__).parent / "results"
sys.path.insert(0, str(Path(__file__).parent))

OPERATOR_POLL_INTERVAL_S = 5.0
OPERATOR_POLL_MAX_S = 60.0
OPERATOR_DECISION_LATENCY_S = 8.0

SCHEDULED_DAG_CRON = "0 2 * * 0"
SCHEDULED_DETECTION_AVG_S = 3.5 * 86400
SCHEDULED_DETECTION_MAX_S = 7 * 86400
# Compose-window monitoring DAG. Kind's joint_retrain_dag has schedule=None.
CLOSEDLOOP_DAG_CRON = "*/30 * * * *"
CLOSEDLOOP_DETECTION_AVG_S = 15 * 60
CLOSEDLOOP_DETECTION_MAX_S = 30 * 60

KIND_PROFILE_TO_SCENARIO = {
    "stable": "healthy",
    "drifted": "feature_drift",
    "severe_drift": "regression",
}


class Target:
    def __init__(self, runtime: str, model: str | None = None):
        self.runtime = runtime
        if runtime == "k8s":
            from k8s_runtime import BACKEND_URL, MODEL, assert_kind_context, set_model

            assert_kind_context()
            self.backend = BACKEND_URL
            self.model = set_model(model) if model else MODEL
            self.train_timeout = 300.0
        else:
            self.backend = "http://localhost:8170"
            self.model = model or "customer-churn"
            self.train_timeout = 120.0

    def current_champion(self) -> dict:
        versions = requests.get(f"{self.backend}/api/v1/models/{self.model}/versions", timeout=10).json()
        return next(v for v in versions if v["is_champion"])

    def trigger_training(self, trigger_type: str, scenario: str = "feature_drift"):
        return requests.post(
            f"{self.backend}/api/v1/models/{self.model}/training",
            json={
                "trigger_type": trigger_type,
                "scenario": scenario,
                "trigger_detail": f"Paper B Table 3 A/B/C comparison ({trigger_type})",
            },
            timeout=self.train_timeout,
        )

    def monitoring_check(self, profile: str, auto_retrain: bool) -> dict:
        resp = requests.post(
            f"{self.backend}/api/v1/models/{self.model}/monitoring/check",
            json={"profile": profile, "auto_retrain": auto_retrain},
            timeout=60,
        )
        return resp.json()

    def joint_cell(self, scenario: str, seed: int) -> dict:
        resp = requests.get(
            f"{self.backend}/api/v1/models/{self.model}/joint-cell",
            params={"scenario": scenario, "seed": seed},
            timeout=60,
        )
        return resp.json()

    def joint_retrain(self, scenario: str, seed: int) -> dict:
        resp = requests.post(
            f"{self.backend}/api/v1/models/{self.model}/joint-retrain",
            json={
                "scenario": scenario,
                "seed": seed,
                "trigger_detail": "Paper B kind-window Approach C (joint cell)",
            },
            timeout=self.train_timeout,
        )
        return resp.json()


def _stage_detail(stage: dict) -> dict:
    detail = stage.get("detail")
    if isinstance(detail, dict):
        return detail
    raw = stage.get("detail_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _outcome_summary(pre_champion: dict, run_payload: dict) -> dict:
    outcome = run_payload.get("outcome")
    candidate_f1 = None
    gate_reasons = None
    regression_pct = None
    candidate_recall = None
    for stage in run_payload.get("stages", []) or []:
        name = stage.get("stage_name")
        detail = _stage_detail(stage)
        if name == "evaluate_model":
            candidate_f1 = detail.get("test_f1")
        if name in ("quality_gate", "evaluation_gate"):
            gate_reasons = detail.get("reasons")
            regression_pct = detail.get("regression_pct")
    if outcome == "PROMOTED":
        quality_f1 = candidate_f1
        promoted = True
    else:
        quality_f1 = pre_champion.get("test_f1")
        promoted = False
    return {
        "pipeline_status": run_payload.get("status"),
        "pipeline_outcome": outcome,
        "candidate_test_f1": candidate_f1,
        "candidate_recall": candidate_recall,
        "production_f1_after": quality_f1,
        "promoted": promoted,
        "gate_reasons": gate_reasons,
        "gate_regression_pct": regression_pct,
    }


def _noticed(check: dict, runtime: str) -> str | None:
    if runtime == "k8s":
        if check.get("drift_level") in ("WARNING", "SIGNIFICANT"):
            return check["drift_level"]
        if check.get("evaluation_level") == "BAD":
            return "EVAL_BAD"
        return None
    if check.get("overall_status") in ("WARNING", "CRITICAL"):
        return check["overall_status"]
    return None


def run_approach_c(target: Target, profile: str, scenario: str) -> dict:
    pre = target.current_champion()
    t0 = time.monotonic()
    if target.runtime == "k8s":
        payload = target.joint_retrain(scenario, seed=9801)
        elapsed = round(time.monotonic() - t0, 3)
        decision = payload.get("decision") or {}
        result = {
            "approach": "C - Closed-loop",
            "detection_time_seconds_measured": elapsed if not payload.get("trained") else 0.0,
            "detection_time_note": (
                f"Live POST /joint-retrain latency {elapsed}s on kind. "
                "Airflow joint_retrain_dag.py has schedule=None (manual/conf only), so there is "
                "no 30-minute production poll cadence on this cluster — detection here is the "
                "joint-cell call itself, not an analytical cron wait."
            ),
            "drift_level": decision.get("drift_level"),
            "evaluation_level": decision.get("evaluation_level"),
            "joint_retrain": decision.get("joint_retrain"),
            "psi_mean": decision.get("psi_mean"),
            "matrix_cell": decision.get("matrix_cell"),
            "triggered_retrain_live": bool(payload.get("trained")),
            "total_call_latency_seconds": elapsed,
            "operational_human_actions": 0,
        }
        if payload.get("trained") and payload.get("run"):
            result["recovery_time_seconds"] = elapsed
            result.update(_outcome_summary(pre, payload["run"]))
        else:
            result["recovery_time_seconds"] = None
            result["note"] = (
                "Joint cell did NOT fire (Retrain = SIGNIFICANT and EvaluationLevel != GOOD). "
                "Supplementary forced POST /training trigger_type=joint follows so recovery time "
                "can still be compared; it is not a live autonomous retrain."
            )
            t1 = time.monotonic()
            forced = target.trigger_training(trigger_type="joint", scenario=scenario).json()
            forced_elapsed = round(time.monotonic() - t1, 3)
            result["supplementary_forced_recovery_time_seconds"] = forced_elapsed
            result["supplementary_forced_outcome"] = _outcome_summary(pre, forced)
        return result

    resp = target.monitoring_check(profile, auto_retrain=True)
    elapsed = round(time.monotonic() - t0, 3)
    result = {
        "approach": "C - Closed-loop",
        "detection_time_seconds_measured": 0.0,
        "detection_time_note": (
            f"Live check-call latency measured at {elapsed}s. In production this check runs on a "
            f"{CLOSEDLOOP_DAG_CRON} schedule (monitoring_pipeline_dag.py), so real-world drift-onset-to-check "
            f"latency averages {CLOSEDLOOP_DETECTION_AVG_S/60:.0f} min (max {CLOSEDLOOP_DETECTION_MAX_S/60:.0f} min) — analytical, not measured here."
        ),
        "drift_level": resp.get("drift_level"),
        "evaluation_level": resp.get("evaluation_level"),
        "overall_status": resp.get("overall_status"),
        "triggered_retrain_live": resp.get("triggered_retrain"),
        "total_call_latency_seconds": elapsed,
        "operational_human_actions": 0,
    }
    if resp.get("triggered_retrain"):
        run_id = resp["retrain_run_id"]
        run_payload = requests.get(f"{target.backend}/api/v1/models/{target.model}/training/{run_id}", timeout=30).json()
        result["recovery_time_seconds"] = elapsed
        result.update(_outcome_summary(pre, run_payload))
    else:
        result["recovery_time_seconds"] = None
        result["note"] = (
            "Auto-retrain did NOT fire on this live check (should_retrain()==False). "
            "Supplementary forced trigger_type='drift' follows."
        )
        t1 = time.monotonic()
        forced = target.trigger_training(trigger_type="drift", scenario="feature_drift").json()
        result["supplementary_forced_recovery_time_seconds"] = round(time.monotonic() - t1, 3)
        result["supplementary_forced_outcome"] = _outcome_summary(pre, forced)
    return result


def run_approach_b(target: Target, scenario: str) -> dict:
    pre = target.current_champion()
    t0 = time.monotonic()
    run_payload = target.trigger_training(trigger_type="schedule", scenario=scenario).json()
    elapsed = round(time.monotonic() - t0, 3)
    result = {
        "approach": "B - Scheduled (weekly)",
        "detection_time_seconds_measured": None,
        "detection_time_note": (
            f"Not live-measured: Approach B retrains on {SCHEDULED_DAG_CRON} "
            f"(retraining_dag.py / training_pipeline_dag.py) regardless of drift — "
            f"average {SCHEDULED_DETECTION_AVG_S/86400:.1f} days, max {SCHEDULED_DETECTION_MAX_S/86400:.0f} days. Analytical."
        ),
        "recovery_time_seconds": elapsed,
        "operational_human_actions": 0,
    }
    result.update(_outcome_summary(pre, run_payload))
    return result


def run_approach_a(target: Target, profile: str, scenario: str) -> dict:
    pre = target.current_champion()
    t0 = time.monotonic()
    polls = 0
    noticed_status = None
    last_check = {}
    while time.monotonic() - t0 < OPERATOR_POLL_MAX_S:
        polls += 1
        last_check = (
            target.joint_cell(scenario, seed=9802)
            if target.runtime == "k8s"
            else target.monitoring_check(profile, auto_retrain=False)
        )
        noticed_status = _noticed(last_check, target.runtime)
        if noticed_status:
            break
        time.sleep(OPERATOR_POLL_INTERVAL_S)
    detection_polling_time = round(time.monotonic() - t0, 3)
    time.sleep(OPERATOR_DECISION_LATENCY_S)
    detection_time_total = round(detection_polling_time + OPERATOR_DECISION_LATENCY_S, 3)

    t1 = time.monotonic()
    run_payload = target.trigger_training(trigger_type="manual", scenario=scenario).json()
    recovery_time = round(time.monotonic() - t1, 3)

    result = {
        "approach": "A - Manual",
        "polls_before_notice": polls,
        "noticed_status": noticed_status,
        "last_check": {
            k: last_check.get(k)
            for k in ("drift_level", "evaluation_level", "overall_status", "psi_mean", "joint_retrain")
            if k in last_check
        },
        "detection_polling_time_seconds_measured": detection_polling_time,
        "simulated_decision_latency_seconds": OPERATOR_DECISION_LATENCY_S,
        "detection_time_seconds_measured": detection_time_total,
        "detection_time_note": (
            f"Polling interval ({OPERATOR_POLL_INTERVAL_S}s) and decision latency ({OPERATOR_DECISION_LATENCY_S}s) "
            "are explicitly compressed proxies, not empirically observed human behavior."
        ),
        "recovery_time_seconds": recovery_time,
        "operational_human_actions": 2,
    }
    result.update(_outcome_summary(pre, run_payload))
    return result


def _one_matrix_cell(target: Target, profile: str, scenario: str) -> dict:
    pre = target.current_champion()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": target.runtime,
        "profile": profile,
        "scenario": scenario,
        "model": target.model,
        "backend": target.backend,
        "pre_champion_version": pre.get("version"),
        "methodology_note": (
            "All three approaches use the same 16-stage training pipeline. "
            + (
                f"Kind window: generator scenario='{scenario}' (profile {profile} mapped). "
                "Approach C uses POST /joint-retrain; A polls GET /joint-cell."
                if target.runtime == "k8s"
                else "Compose window: scenario='feature_drift'; A/C use POST /monitoring/check."
            )
        ),
        "approach_c": run_approach_c(target, profile, scenario),
        "approach_b": run_approach_b(target, scenario),
        "approach_a": run_approach_a(target, profile, scenario),
    }
    post = target.current_champion()
    report["post_champion_version"] = post.get("version")
    report["champion_walked"] = pre.get("version") != post.get("version")
    return report


def _write_report(path: Path, payload: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Wrote {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=["compose", "k8s"], default="compose")
    parser.add_argument("--profile", default="severe_drift", choices=["stable", "drifted", "severe_drift"])
    parser.add_argument("--model", default=None, help="Override model (kind default: churn-predictor). Use a dedicated model for n≥3 so the published champion does not walk.")
    parser.add_argument("--repeats", type=int, default=1, help="Repeat the A/B/C cell. Writes *_repeats.json and does not overwrite the published Table 3 file.")
    parser.add_argument("--overwrite-published", action="store_true", help="Allow replacing approach_comparison_{profile}[_kind].json (the Table 3 source).")
    args = parser.parse_args()

    target = Target(args.runtime, model=args.model)
    assert requests.get(f"{target.backend}/ready", timeout=5).json().get("ready"), "backend not ready"

    scenario = KIND_PROFILE_TO_SCENARIO[args.profile] if args.runtime == "k8s" else "feature_drift"
    published = RESULTS_DIR / (
        f"approach_comparison_{args.profile}_kind.json" if args.runtime == "k8s" else f"approach_comparison_{args.profile}.json"
    )

    if args.repeats > 1:
        trials = [_one_matrix_cell(target, args.profile, scenario) for _ in range(args.repeats)]
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime": args.runtime,
            "profile": args.profile,
            "scenario": scenario,
            "model": target.model,
            "repeats": args.repeats,
            "champion_walked_any": any(t.get("champion_walked") for t in trials),
            "trials": trials,
        }
        suffix = f"{args.profile}_kind_repeats.json" if args.runtime == "k8s" else f"{args.profile}_repeats.json"
        _write_report(RESULTS_DIR / f"approach_comparison_{suffix}", payload)
        print(json.dumps(payload, indent=2, default=str))
        return

    report = _one_matrix_cell(target, args.profile, scenario)
    if published.exists() and not args.overwrite_published:
        alt = published.with_name(published.stem + "_run.json")
        _write_report(alt, report)
        print(f"left published Table 3 file untouched: {published}")
    else:
        _write_report(published, report)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

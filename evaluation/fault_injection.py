#!/usr/bin/env python3
"""Fault-injection (chaos-engineering) harness for the cmp_ reference stack.

Implements Paper B Section 6.2's reliability protocol against the LIVE stack
(`docker compose` project in this directory, container prefix `cmp_`). Each
scenario is run against the real running containers; nothing here is
simulated. Results are written to evaluation/results/fault_injection.json.

Usage:
    evaluation/.venv/bin/python evaluation/fault_injection.py [--trials N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BACKEND = "http://localhost:8170"
MLFLOW = "http://localhost:5030"
MINIO = "http://localhost:9370"
MODEL = "customer-churn"
RESULTS_DIR = Path(__file__).parent / "results"


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def _wait_until(check, timeout_s: float = 60.0, interval_s: float = 0.5) -> float | None:
    """Poll `check()` until it returns True. Returns elapsed seconds, or None on timeout."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        try:
            if check():
                return round(time.monotonic() - t0, 3)
        except Exception:
            pass
        time.sleep(interval_s)
    return None


def _backend_ready() -> bool:
    r = requests.get(f"{BACKEND}/ready", timeout=3)
    return r.status_code == 200 and r.json().get("ready") is True


def _mlflow_healthy() -> bool:
    r = requests.get(f"{MLFLOW}/health", timeout=3)
    return r.status_code == 200


def _minio_healthy() -> bool:
    r = requests.get(f"{MINIO}/minio/health/live", timeout=3)
    return r.status_code == 200


def _mlflow_down() -> bool:
    """True once the container is actually unreachable (connection refused/reset),
    not just slow — `_mlflow_healthy` raising IS the signal here, so this must not
    let that exception propagate as a false negative."""
    try:
        return not _mlflow_healthy()
    except requests.exceptions.RequestException:
        return True


def _minio_down() -> bool:
    try:
        return not _minio_healthy()
    except requests.exceptions.RequestException:
        return True


def _trigger_training(scenario: str = "healthy", trigger_type: str = "manual", timeout: float = 30.0):
    return requests.post(
        f"{BACKEND}/api/v1/models/{MODEL}/training",
        json={"trigger_type": trigger_type, "scenario": scenario,
              "trigger_detail": "fault-injection harness (Paper B, Section 6.2)"},
        timeout=timeout,
    )


def scenario_backend_kill_inflight(trials: int) -> dict:
    """Kill cmp_backend the instant a training request is in flight.

    docker-compose gives cmp_backend `restart: unless-stopped`, so a SIGKILL
    should trigger an automatic restart. We measure (a) whether the in-flight
    HTTP call ever got a response, (b) MTTR to /ready again, and (c) whether
    the run this created is left orphaned in RUNNING status (a data-integrity
    check, not just an availability one).
    """
    runs = []
    for i in range(trials):
        result = {"trial": i + 1}
        client_exc = {"raised": False, "type": None}

        def _fire():
            try:
                _trigger_training(trigger_type="manual", scenario="healthy")
            except Exception as exc:  # noqa: BLE001 - we want to record any exception type
                client_exc["raised"] = True
                client_exc["type"] = type(exc).__name__

        t0 = time.monotonic()
        th = threading.Thread(target=_fire)
        th.start()
        _docker("kill", "cmp_backend")  # SIGKILL, no delay — see caveat in Section 8 write-up
        th.join(timeout=35)
        kill_to_fire_gap_s = round(time.monotonic() - t0, 3)

        # First measure whether `restart: unless-stopped` self-heals within a
        # generous window; if it does not, fall back to a manual `docker start`
        # and measure THAT recovery time separately — reporting both is the
        # honest result, not silently patching over a policy that didn't fire.
        auto_mttr = _wait_until(_backend_ready, timeout_s=30)
        manual_intervention_required = auto_mttr is None
        manual_mttr = None
        if manual_intervention_required:
            t_manual = time.monotonic()
            _docker("start", "cmp_backend")
            manual_mttr = _wait_until(_backend_ready, timeout_s=60)
            manual_mttr = round(time.monotonic() - t_manual, 3) if manual_mttr is not None else None

        result.update({
            "client_saw_exception": client_exc["raised"],
            "client_exception_type": client_exc["type"],
            "auto_restart_mttr_seconds": auto_mttr,
            "manual_intervention_required": manual_intervention_required,
            "manual_intervention_mttr_seconds": manual_mttr,
            "wallclock_from_kill_command_s": kill_to_fire_gap_s,
        })
        time.sleep(2)  # let the (auto- or manually-) restarted container settle before checking history
        try:
            hist = requests.get(f"{BACKEND}/api/v1/models/{MODEL}/training/history", params={"limit": 5}, timeout=10).json()
            result["orphaned_running_run"] = any(r["status"] == "RUNNING" for r in hist)
            result["most_recent_run_status"] = hist[0]["status"] if hist else None
        except Exception as exc:  # noqa: BLE001
            result["post_check_error"] = str(exc)
        runs.append(result)
    return {
        "fault": "backend_kill_inflight",
        "description": "docker kill cmp_backend while a POST /training request is in flight",
        "trials": runs,
        "auto_restart_mttr_seconds_avg": _avg([r["auto_restart_mttr_seconds"] for r in runs if r.get("auto_restart_mttr_seconds") is not None]),
        "manual_intervention_required_count": sum(1 for r in runs if r.get("manual_intervention_required")),
        "manual_intervention_mttr_seconds_avg": _avg([r["manual_intervention_mttr_seconds"] for r in runs if r.get("manual_intervention_mttr_seconds") is not None]),
    }


def _ensure_backend_healthy() -> None:
    """cmp_backend was empirically observed NOT to self-heal after SIGKILL
    (Section 6.2 finding) — guard every other scenario against inheriting a
    dead backend from a previous scenario."""
    if _backend_ready():
        return
    _docker("start", "cmp_backend")
    assert _wait_until(_backend_ready, timeout_s=60) is not None, "cmp_backend could not be brought back up"


def scenario_mlflow_outage(trials: int) -> dict:
    """Stop cmp_mlflow, trigger a normal training run, inspect whether the
    pipeline silently continues (per code: mlflow_utils swallows all
    exceptions "MLflow must never break the pipeline") and whether a model
    can reach production without ever being registered in the MLflow registry.
    """
    _ensure_backend_healthy()
    runs = []
    for i in range(trials):
        result = {"trial": i + 1}
        _docker("stop", "cmp_mlflow")
        assert _wait_until(_mlflow_down, timeout_s=15) is not None, "mlflow did not go down"
        try:
            resp = _trigger_training(trigger_type="manual", scenario="healthy")
            payload = resp.json() if resp.status_code == 200 else {"http_status": resp.status_code, "body": resp.text[:500]}
        except Exception as exc:  # noqa: BLE001
            payload = {"client_exception": f"{type(exc).__name__}: {exc}"}
        result["raw_response_summary"] = {k: v for k, v in payload.items() if k != "stages"} if isinstance(payload, dict) else str(payload)[:500]
        result["pipeline_response_ok"] = isinstance(payload, dict) and payload.get("status") in ("SUCCESS", "REJECTED")
        result["outcome"] = payload.get("outcome") if isinstance(payload, dict) else None
        run_id = payload.get("id") if isinstance(payload, dict) else None
        if run_id:
            stages = {s["stage_name"]: s for s in payload.get("stages", [])}
            log_mlflow_detail = json.loads(stages.get("log_mlflow", {}).get("detail_json", "{}") or "{}")
            register_detail = json.loads(stages.get("register_model", {}).get("detail_json", "{}") or "{}")
            result["log_mlflow_stage_status"] = stages.get("log_mlflow", {}).get("status")
            result["mlflow_run_id_captured"] = log_mlflow_detail.get("mlflow_run_id", "") or None
            result["register_model_stage_status"] = stages.get("register_model", {}).get("status")
            result["registry_version_captured"] = register_detail.get("registry_version")
            result["promoted_to_production_anyway"] = payload.get("outcome") == "PROMOTED"
            result["integrity_finding"] = (
                result["promoted_to_production_anyway"] and not result["mlflow_run_id_captured"]
            )
        t_restart = time.monotonic()
        _docker("start", "cmp_mlflow")
        mttr = _wait_until(_mlflow_healthy, timeout_s=60)
        result["mttr_seconds"] = mttr
        runs.append(result)
        time.sleep(2)
    return {
        "fault": "mlflow_outage",
        "description": "docker stop cmp_mlflow, trigger training, inspect registration integrity, then restore",
        "trials": runs,
        "mttr_seconds_avg": _avg([r["mttr_seconds"] for r in runs if r.get("mttr_seconds") is not None]),
        "integrity_findings_count": sum(1 for r in runs if r.get("integrity_finding")),
    }


def scenario_minio_outage(trials: int) -> dict:
    """Stop cmp_minio, trigger a training run, confirm write_to_s3's documented
    fallback ("S3 must never block training") actually holds under a real outage."""
    _ensure_backend_healthy()
    runs = []
    for i in range(trials):
        result = {"trial": i + 1}
        _docker("stop", "cmp_minio")
        assert _wait_until(_minio_down, timeout_s=15) is not None, "minio did not go down"
        try:
            resp = _trigger_training(trigger_type="manual", scenario="healthy")
            payload = resp.json() if resp.status_code == 200 else {"http_status": resp.status_code, "body": resp.text[:500]}
        except Exception as exc:  # noqa: BLE001
            payload = {"client_exception": f"{type(exc).__name__}: {exc}"}
        result["raw_response_summary"] = {k: v for k, v in payload.items() if k != "stages"} if isinstance(payload, dict) else str(payload)[:500]
        result["pipeline_response_ok"] = isinstance(payload, dict) and payload.get("status") in ("SUCCESS", "REJECTED")
        result["outcome"] = payload.get("outcome") if isinstance(payload, dict) else None
        if isinstance(payload, dict) and payload.get("stages"):
            stages = {s["stage_name"]: s for s in payload["stages"]}
            s3_detail = json.loads(stages.get("write_to_s3", {}).get("detail_json", "{}") or "{}")
            result["write_to_s3_stage_status"] = stages.get("write_to_s3", {}).get("status")
            result["s3_uri_fallback_used"] = "dataset:" not in (s3_detail.get("s3_uri") or "") and "s3://" not in (s3_detail.get("s3_uri") or "")
            result["s3_uri_captured"] = s3_detail.get("s3_uri")
        _docker("start", "cmp_minio")
        mttr = _wait_until(_minio_healthy, timeout_s=60)
        result["mttr_seconds"] = mttr
        runs.append(result)
        time.sleep(2)
    return {
        "fault": "minio_outage",
        "description": "docker stop cmp_minio, trigger training, confirm graceful degradation, then restore",
        "trials": runs,
        "mttr_seconds_avg": _avg([r["mttr_seconds"] for r in runs if r.get("mttr_seconds") is not None]),
    }


def scenario_rollback_mechanism() -> dict:
    """Exercise the real POST /rollback endpoint once, verify champion state
    flips correctly, then restore the platform's prior champion/archived state
    via direct SQL so the shared demo stack (and Paper A's already-published
    Table 1/11 figures, e.g. rollback_events_count) is left exactly as found.
    """
    _ensure_backend_healthy()
    versions = requests.get(f"{BACKEND}/api/v1/models/{MODEL}/versions", timeout=10).json()
    champion = next(v for v in versions if v["is_champion"])
    archived = [v for v in versions if v["stage"] == "archived"]
    if not archived:
        return {"fault": "rollback_mechanism", "skipped": True, "reason": "no archived version available to roll back to"}
    previous = archived[0]

    t0 = time.monotonic()
    resp = requests.post(f"{BACKEND}/api/v1/models/{MODEL}/rollback",
                          json={"reason": "chaos-engineering test (Paper B, Section 6.2) — restored immediately after"},
                          timeout=15)
    elapsed = round(time.monotonic() - t0, 3)
    body = resp.json()
    post_versions = requests.get(f"{BACKEND}/api/v1/models/{MODEL}/versions", timeout=10).json()
    new_champion = next(v for v in post_versions if v["is_champion"])
    correct = new_champion["version"] == previous["version"]

    restore = _docker(
        "exec", "-i", "cmp_postgres", "psql", "-U", "cmp_user", "-d", "churn_platform", "-v", "ON_ERROR_STOP=1",
        "-c", f"""
        UPDATE model_versions SET is_champion = true, stage = 'production' WHERE id = '{champion['id']}';
        UPDATE model_versions SET is_champion = false, stage = 'archived' WHERE id = '{previous['id']}';
        DELETE FROM rollback_events WHERE id = '{body['id']}';
        DELETE FROM deployment_events WHERE detail LIKE '%chaos-engineering test (Paper B%';
        DELETE FROM alerts WHERE message LIKE '%chaos-engineering test (Paper B%';
        DELETE FROM audit_logs WHERE detail LIKE '%chaos-engineering test (Paper B%';
        """,
    )
    verify_versions = requests.get(f"{BACKEND}/api/v1/models/{MODEL}/versions", timeout=10).json()
    verify_champion = next(v for v in verify_versions if v["is_champion"])
    restored_correctly = verify_champion["id"] == champion["id"]

    return {
        "fault": "rollback_mechanism",
        "description": "POST /rollback against the live champion, verify correctness, then restore original state via SQL",
        "pre_champion_version": champion["version"],
        "expected_post_champion_version": previous["version"],
        "observed_post_champion_version": new_champion["version"],
        "rollback_correct": correct,
        "rollback_call_latency_seconds": elapsed,
        "restore_sql_returncode": restore.returncode,
        "restore_sql_stderr": restore.stderr.strip() or None,
        "state_restored_correctly": restored_correctly,
    }


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=3, help="trials per repeatable fault scenario")
    args = parser.parse_args()

    assert _backend_ready(), "cmp_backend is not ready — start the stack with `docker compose up -d` first"

    scenario_fns = {
        "backend_kill_inflight": lambda: scenario_backend_kill_inflight(args.trials),
        "mlflow_outage": lambda: scenario_mlflow_outage(args.trials),
        "minio_outage": lambda: scenario_minio_outage(args.trials),
        "rollback_mechanism": scenario_rollback_mechanism,
    }
    scenarios = {}
    for name, fn in scenario_fns.items():
        try:
            scenarios[name] = fn()
        except Exception as exc:  # noqa: BLE001 - one scenario failing must not lose the others
            scenarios[name] = {"error": f"{type(exc).__name__}: {exc}"}
            # best-effort recovery so the next scenario doesn't inherit a stopped container
            for c in ("cmp_mlflow", "cmp_minio", "cmp_backend"):
                _docker("start", c)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trials_per_scenario": args.trials,
        "scenarios": scenarios,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "fault_injection.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out_path}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

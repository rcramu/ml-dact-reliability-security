#!/usr/bin/env python3
"""Fault-injection harness for Paper B (Section 6.2).

Two observation windows, selected with ``--runtime``:

  compose  Archived Docker Compose snapshot (`cmp_*`, model `customer-churn`,
           backend http://localhost:8170). Writes ``results/fault_injection.json``.
  k8s      Paper A's local-EKS kind cluster (`kind-dact-local-eks`, namespace
           ``dact``, model ``churn-predictor``, backend http://127.0.0.1:8166).
           Writes ``results/fault_injection_kind.json``. Every kubectl call is
           pinned to that context; the process default kubecontext is never used.

Usage:
    evaluation/.venv/bin/python evaluation/fault_injection.py --runtime compose --trials 5
    evaluation/.venv/bin/python evaluation/fault_injection.py --runtime k8s --trials 5
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

RESULTS_DIR = Path(__file__).parent / "results"

# Compose-window defaults (archived snapshot).
COMPOSE_BACKEND = "http://localhost:8170"
COMPOSE_MLFLOW = "http://localhost:5030"
COMPOSE_MINIO = "http://localhost:9370"
COMPOSE_MODEL = "customer-churn"

# Designed self-heal bound used to falsify H1 (same 30 s window as the paper).
AUTO_HEAL_BOUND_S = 30.0


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def _wait_until(check, timeout_s: float = 60.0, interval_s: float = 0.5) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        try:
            if check():
                return round(time.monotonic() - t0, 3)
        except Exception:
            pass
        time.sleep(interval_s)
    return None


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return round(var ** 0.5, 3)


# ---------------------------------------------------------------------------
# Shared HTTP helpers (backend/mlflow URLs come from the selected runtime)
# ---------------------------------------------------------------------------


class Stack:
    def __init__(self, runtime: str):
        self.runtime = runtime
        if runtime == "k8s":
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from k8s_runtime import (  # noqa: WPS433 - local import keeps compose path free of kubectl
                BACKEND_URL,
                MLFLOW_URL,
                MODEL,
                assert_kind_context,
                collect_environment,
                delete_pods_by_app,
                exec_python_in_backend,
                psql,
                require_uuid,
                pod_ready_count,
                pod_uids,
                rollout_status,
                scale_deployment,
            )

            assert_kind_context()
            self.backend = BACKEND_URL
            self.mlflow = MLFLOW_URL
            self.minio = None
            self.model = MODEL
            self.delete_pods_by_app = delete_pods_by_app
            self.scale_deployment = scale_deployment
            self.rollout_status = rollout_status
            self.psql = psql
            self.require_uuid = require_uuid
            self.exec_python_in_backend = exec_python_in_backend
            self.pod_uids = pod_uids
            self.pod_ready_count = pod_ready_count
            self.environment = collect_environment()
        else:
            self.backend = COMPOSE_BACKEND
            self.mlflow = COMPOSE_MLFLOW
            self.minio = COMPOSE_MINIO
            self.model = COMPOSE_MODEL
            self.environment = {"runtime": "compose", "backend": COMPOSE_BACKEND}

    def backend_ready(self) -> bool:
        r = requests.get(f"{self.backend}/ready", timeout=3)
        return r.status_code == 200 and r.json().get("ready") is True

    def mlflow_healthy(self) -> bool:
        r = requests.get(f"{self.mlflow}/health", timeout=3)
        return r.status_code == 200

    def minio_healthy(self) -> bool:
        if not self.minio:
            return False
        r = requests.get(f"{self.minio}/minio/health/live", timeout=3)
        return r.status_code == 200

    def mlflow_down(self) -> bool:
        try:
            return not self.mlflow_healthy()
        except requests.exceptions.RequestException:
            return True

    def minio_down(self) -> bool:
        try:
            return not self.minio_healthy()
        except requests.exceptions.RequestException:
            return True

    def trigger_training(self, scenario: str = "healthy", trigger_type: str = "manual", timeout: float = 30.0):
        return requests.post(
            f"{self.backend}/api/v1/models/{self.model}/training",
            json={
                "trigger_type": trigger_type,
                "scenario": scenario,
                "trigger_detail": "fault-injection harness (Paper B, Section 6.2)",
            },
            timeout=timeout,
        )

    def ensure_backend_healthy(self) -> None:
        if self.backend_ready():
            return
        if self.runtime == "k8s":
            self.rollout_status("backend", timeout_s=180)
            assert _wait_until(self.backend_ready, timeout_s=90) is not None, "kind backend did not return"
            return
        _docker("start", "cmp_backend")
        assert _wait_until(self.backend_ready, timeout_s=60) is not None, "cmp_backend could not be brought back up"

    def inject_backend_kill(self) -> None:
        if self.runtime == "k8s":
            self.delete_pods_by_app("backend")
            return
        _docker("kill", "cmp_backend")

    def inject_mlflow_down(self) -> None:
        if self.runtime == "k8s":
            self.scale_deployment("mlflow", 0)
            return
        _docker("stop", "cmp_mlflow")

    def restore_mlflow(self) -> None:
        if self.runtime == "k8s":
            self.scale_deployment("mlflow", 1)
            self.rollout_status("mlflow", timeout_s=120)
            return
        _docker("start", "cmp_mlflow")

    def inject_minio_down(self) -> None:
        if self.runtime == "k8s":
            raise RuntimeError("MinIO is not deployed on the kind stack")
        _docker("stop", "cmp_minio")

    def restore_minio(self) -> None:
        if self.runtime == "k8s":
            return
        _docker("start", "cmp_minio")

    def restore_backend_manual(self) -> None:
        if self.runtime == "k8s":
            self.scale_deployment("backend", 1)
            self.rollout_status("backend", timeout_s=180)
            return
        _docker("start", "cmp_backend")


def scenario_backend_kill_inflight(stack: Stack, trials: int) -> dict:
    runs = []
    for i in range(trials):
        result = {"trial": i + 1}
        client_exc = {"raised": False, "type": None}

        def _fire():
            try:
                stack.trigger_training(trigger_type="manual", scenario="healthy", timeout=35)
            except Exception as exc:  # noqa: BLE001
                client_exc["raised"] = True
                client_exc["type"] = type(exc).__name__

        old_uids = stack.pod_uids("backend") if stack.runtime == "k8s" else []
        t0 = time.monotonic()
        th = threading.Thread(target=_fire)
        th.start()
        time.sleep(0.4)  # let the in-flight POST leave the client
        stack.inject_backend_kill()

        def _healed() -> bool:
            if stack.runtime == "k8s":
                new_uids = stack.pod_uids("backend")
                if not new_uids or set(new_uids) & set(old_uids):
                    return False
                if stack.pod_ready_count("backend") < 1:
                    return False
            return stack.backend_ready()

        auto_mttr = _wait_until(_healed, timeout_s=AUTO_HEAL_BOUND_S, interval_s=0.25)
        th.join(timeout=40)
        kill_to_fire_gap_s = round(time.monotonic() - t0, 3)
        manual_intervention_required = auto_mttr is None
        manual_mttr = None
        if manual_intervention_required:
            t_manual = time.monotonic()
            stack.restore_backend_manual()
            recovered = _wait_until(stack.backend_ready, timeout_s=90)
            manual_mttr = round(time.monotonic() - t_manual, 3) if recovered is not None else None

        result.update({
            "client_saw_exception": client_exc["raised"],
            "client_exception_type": client_exc["type"],
            "auto_restart_mttr_seconds": auto_mttr,
            "manual_intervention_required": manual_intervention_required,
            "manual_intervention_mttr_seconds": manual_mttr,
            "wallclock_from_kill_command_s": kill_to_fire_gap_s,
            "designed_auto_heal_bound_s": AUTO_HEAL_BOUND_S,
        })
        time.sleep(2)
        try:
            hist = requests.get(
                f"{stack.backend}/api/v1/models/{stack.model}/training/history",
                params={"limit": 5},
                timeout=10,
            ).json()
            result["orphaned_running_run"] = any(r.get("status") == "RUNNING" for r in hist)
            result["most_recent_run_status"] = hist[0]["status"] if hist else None
        except Exception as exc:  # noqa: BLE001
            result["post_check_error"] = str(exc)
        runs.append(result)

    auto_vals = [r["auto_restart_mttr_seconds"] for r in runs if r.get("auto_restart_mttr_seconds") is not None]
    manual_vals = [r["manual_intervention_mttr_seconds"] for r in runs if r.get("manual_intervention_mttr_seconds") is not None]
    recovered = sum(1 for r in runs if not r.get("manual_intervention_required"))
    return {
        "fault": "backend_kill_inflight",
        "description": (
            "kind: kubectl delete pod -l app=backend while POST /training is in flight"
            if stack.runtime == "k8s"
            else "docker kill cmp_backend while a POST /training request is in flight"
        ),
        "trials": runs,
        "auto_restart_mttr_seconds_avg": _avg(auto_vals),
        "auto_restart_mttr_seconds_sd": _sd(auto_vals),
        "manual_intervention_required_count": sum(1 for r in runs if r.get("manual_intervention_required")),
        "manual_intervention_mttr_seconds_avg": _avg(manual_vals),
        "availability": recovered / len(runs) if runs else None,
        "error_rate": (len(runs) - recovered) / len(runs) if runs else None,
    }


def scenario_mlflow_outage(stack: Stack, trials: int) -> dict:
    stack.ensure_backend_healthy()
    runs = []
    for i in range(trials):
        result = {"trial": i + 1}
        if stack.runtime == "k8s":
            stack.scale_deployment("mlflow", 0)
            stack.delete_pods_by_app("mlflow")
        else:
            stack.inject_mlflow_down()
        assert _wait_until(stack.mlflow_down, timeout_s=45) is not None, "mlflow did not go down"
        try:
            resp = stack.trigger_training(trigger_type="manual", scenario="healthy", timeout=45)
            payload = resp.json() if resp.status_code == 200 else {"http_status": resp.status_code, "body": resp.text[:500]}
        except Exception as exc:  # noqa: BLE001
            payload = {"client_exception": f"{type(exc).__name__}: {exc}"}
        result["raw_response_summary"] = (
            {k: v for k, v in payload.items() if k != "stages"} if isinstance(payload, dict) else str(payload)[:500]
        )
        result["pipeline_response_ok"] = isinstance(payload, dict) and payload.get("status") in ("SUCCESS", "REJECTED")
        result["outcome"] = payload.get("outcome") if isinstance(payload, dict) else None
        if isinstance(payload, dict) and payload.get("stages"):
            stages = {s["stage_name"]: s for s in payload.get("stages", [])}
            log_stage = stages.get("log_mlflow", {})
            detail = log_stage.get("detail") or {}
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail or "{}")
                except json.JSONDecodeError:
                    detail = {}
            result["log_mlflow_stage_status"] = log_stage.get("status")
            result["mlflow_run_id_captured"] = detail.get("mlflow_run_id") or None
            result["promoted_to_production_anyway"] = payload.get("outcome") == "PROMOTED"
            result["integrity_finding"] = bool(
                result["promoted_to_production_anyway"] and not result["mlflow_run_id_captured"]
            )
        t_restart = time.monotonic()
        stack.restore_mlflow()
        mttr = _wait_until(stack.mlflow_healthy, timeout_s=90)
        result["mttr_seconds"] = mttr
        result["restore_elapsed_s"] = round(time.monotonic() - t_restart, 3)
        runs.append(result)
        time.sleep(2)

    mttrs = [r["mttr_seconds"] for r in runs if r.get("mttr_seconds") is not None]
    ok = sum(1 for r in runs if r.get("pipeline_response_ok"))
    return {
        "fault": "mlflow_outage",
        "description": (
            "kind: scale deployment/mlflow to 0, trigger training, then restore"
            if stack.runtime == "k8s"
            else "docker stop cmp_mlflow, trigger training, inspect registration integrity, then restore"
        ),
        "trials": runs,
        "mttr_seconds_avg": _avg(mttrs),
        "mttr_seconds_sd": _sd(mttrs),
        "integrity_findings_count": sum(1 for r in runs if r.get("integrity_finding")),
        "availability": ok / len(runs) if runs else None,
        "error_rate": (len(runs) - ok) / len(runs) if runs else None,
    }


def scenario_minio_outage(stack: Stack, trials: int) -> dict:
    if stack.runtime == "k8s":
        return {
            "fault": "minio_outage",
            "skipped": True,
            "reason": (
                "The kind stack (Paper A local EKS) has no MinIO Deployment. "
                "Artifacts live on the MLflow PVC (mlflow.yaml --default-artifact-root=/mlflow/artifacts). "
                "This fault is Compose-window only."
            ),
            "trials": [],
            "availability": None,
            "error_rate": None,
        }

    stack.ensure_backend_healthy()
    runs = []
    for i in range(trials):
        result = {"trial": i + 1}
        stack.inject_minio_down()
        assert _wait_until(stack.minio_down, timeout_s=15) is not None, "minio did not go down"
        try:
            resp = stack.trigger_training(trigger_type="manual", scenario="healthy", timeout=45)
            payload = resp.json() if resp.status_code == 200 else {"http_status": resp.status_code, "body": resp.text[:500]}
        except Exception as exc:  # noqa: BLE001
            payload = {"client_exception": f"{type(exc).__name__}: {exc}"}
        result["raw_response_summary"] = (
            {k: v for k, v in payload.items() if k != "stages"} if isinstance(payload, dict) else str(payload)[:500]
        )
        result["pipeline_response_ok"] = isinstance(payload, dict) and payload.get("status") in ("SUCCESS", "REJECTED")
        result["outcome"] = payload.get("outcome") if isinstance(payload, dict) else None
        if isinstance(payload, dict) and payload.get("stages"):
            stages = {s["stage_name"]: s for s in payload["stages"]}
            s3_detail = json.loads(stages.get("write_to_s3", {}).get("detail_json", "{}") or "{}")
            result["write_to_s3_stage_status"] = stages.get("write_to_s3", {}).get("status")
            result["s3_uri_fallback_used"] = "dataset:" not in (s3_detail.get("s3_uri") or "") and "s3://" not in (s3_detail.get("s3_uri") or "")
            result["s3_uri_captured"] = s3_detail.get("s3_uri")
        stack.restore_minio()
        mttr = _wait_until(stack.minio_healthy, timeout_s=60)
        result["mttr_seconds"] = mttr
        runs.append(result)
        time.sleep(2)
    mttrs = [r["mttr_seconds"] for r in runs if r.get("mttr_seconds") is not None]
    ok = sum(1 for r in runs if r.get("pipeline_response_ok"))
    return {
        "fault": "minio_outage",
        "description": "docker stop cmp_minio, trigger training, confirm graceful degradation, then restore",
        "trials": runs,
        "mttr_seconds_avg": _avg(mttrs),
        "mttr_seconds_sd": _sd(mttrs),
        "availability": ok / len(runs) if runs else None,
        "error_rate": (len(runs) - ok) / len(runs) if runs else None,
    }


def scenario_rollback_mechanism(stack: Stack) -> dict:
    stack.ensure_backend_healthy()
    versions = requests.get(f"{stack.backend}/api/v1/models/{stack.model}/versions", timeout=10).json()
    champion = next(v for v in versions if v["is_champion"])
    archived = [v for v in versions if v["stage"] == "archived"]
    if not archived:
        return {"fault": "rollback_mechanism", "skipped": True, "reason": "no archived version available to roll back to"}
    previous = archived[0]

    t0 = time.monotonic()
    resp = requests.post(
        f"{stack.backend}/api/v1/models/{stack.model}/rollback",
        json={"reason": "chaos-engineering test (Paper B, Section 6.2) — restored immediately after"},
        timeout=15,
    )
    elapsed = round(time.monotonic() - t0, 3)
    body = resp.json()
    post_versions = requests.get(f"{stack.backend}/api/v1/models/{stack.model}/versions", timeout=10).json()
    new_champion = next(v for v in post_versions if v["is_champion"])
    correct = new_champion["version"] == previous["version"]

    if stack.runtime == "k8s":
        champ_id = stack.require_uuid(champion["id"], "champion.id")
        prev_id = stack.require_uuid(previous["id"], "previous.id")
        event_id = stack.require_uuid(body["id"], "rollback.id")
        restore = stack.psql(
            f"""
            UPDATE model_versions SET is_champion = true, stage = 'production' WHERE id = '{champ_id}';
            UPDATE model_versions SET is_champion = false, stage = 'archived' WHERE id = '{prev_id}';
            DELETE FROM rollback_events WHERE id = '{event_id}';
            DELETE FROM deployment_events WHERE detail LIKE '%chaos-engineering test (Paper B%';
            DELETE FROM alerts WHERE message LIKE '%chaos-engineering test (Paper B%';
            DELETE FROM audit_logs WHERE detail LIKE '%chaos-engineering test (Paper B%';
            """
        )
    else:
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

    verify_versions = requests.get(f"{stack.backend}/api/v1/models/{stack.model}/versions", timeout=10).json()
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
        "restore_sql_stderr": (restore.stderr or "").strip() or None,
        "state_restored_correctly": restored_correctly,
        "availability": 1.0 if correct else 0.0,
        "error_rate": 0.0 if correct else 1.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=["compose", "k8s"], default="compose")
    parser.add_argument("--trials", type=int, default=3, help="trials per repeatable fault scenario")
    args = parser.parse_args()

    stack = Stack(args.runtime)
    assert stack.backend_ready(), (
        "kind backend is not ready — start it with Paper A's k8s/deploy-local-eks.sh"
        if args.runtime == "k8s"
        else "cmp_backend is not ready — start the stack with `docker compose up -d` first"
    )

    scenario_fns = {
        "backend_kill_inflight": lambda: scenario_backend_kill_inflight(stack, args.trials),
        "mlflow_outage": lambda: scenario_mlflow_outage(stack, args.trials),
        "minio_outage": lambda: scenario_minio_outage(stack, args.trials),
        "rollback_mechanism": lambda: scenario_rollback_mechanism(stack),
    }
    scenarios = {}
    for name, fn in scenario_fns.items():
        try:
            scenarios[name] = fn()
        except Exception as exc:  # noqa: BLE001
            scenarios[name] = {"error": f"{type(exc).__name__}: {exc}"}
            if args.runtime == "k8s":
                try:
                    stack.scale_deployment("mlflow", 1)
                    stack.scale_deployment("backend", 1)
                except Exception:
                    pass
            else:
                for c in ("cmp_mlflow", "cmp_minio", "cmp_backend"):
                    _docker("start", c)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": args.runtime,
        "model": stack.model,
        "backend": stack.backend,
        "trials_per_scenario": args.trials,
        "designed_auto_heal_bound_s": AUTO_HEAL_BOUND_S,
        "environment": stack.environment,
        "scenarios": scenarios,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out_name = "fault_injection_kind.json" if args.runtime == "k8s" else "fault_injection.json"
    out_path = RESULTS_DIR / out_name
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out_path}")
    print(json.dumps({k: v for k, v in report.items() if k != "environment"}, indent=2, default=str))


if __name__ == "__main__":
    main()

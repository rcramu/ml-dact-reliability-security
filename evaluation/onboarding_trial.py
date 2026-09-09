#!/usr/bin/env python3
"""Onboarding-lead-time trial (Paper B, Section 6.4/12).

Protocol: as an engineer who did NOT build this stack, attempt to add a
SECOND monitored model using ONLY the existing documentation (README.md,
EVALUATION.md, the OpenAPI docs at /docs, and the routers' own docstrings)
before reading pipeline_engine.py/seed.py source.

IMPORTANT HONESTY NOTE: this script does NOT claim a numeric "documentation
review" duration. A genuine onboarding-lead-time measurement requires a truly
naive participant who has never seen this codebase; the authors/agent
producing this paper already know the codebase from building/evaluating it
in this same session, so any duration we report for "reading the docs" would
be fabricated, not measured. Only the mechanical, scripted DB-level
onboarding step below is a real, wall-clock-timed action. The documentation
finding itself (there is NO REST endpoint to create a new model) is real and
verifiable independently of timing.

Finding recorded during the documentation pass: there is NO REST endpoint to
create a new model — every write endpoint (`POST /{model}/training`,
`POST /{model}/monitoring/check`, `POST /{model}/rollback`) takes an EXISTING
model name as a path parameter, confirmed by grepping every
`@router.post`/`@router.put` in `backend/app/routers/*.py`. The only way to
add a model is a direct database insert of a `TrainedModel` row — i.e.,
onboarding a new model requires backend code/DB access, not just API calls,
which is itself the answer to RQ4/ISO-25010 "modifiability" for this task.

This script performs that DB-level onboarding directly against the LIVE
cmp_backend container (via `docker exec`, reusing its own SQLAlchemy
session/pipeline_engine code — no new container, no redeploy), verifies the
new model is independently monitorable, and reports the real measured
elapsed time for that mechanical step. It then removes the added rows so the
shared demo stack (and Paper A/B's already-published "single model" scope
statements) are left as found — same test-then-restore pattern already used
for the rollback mechanism test in fault_injection.py.

Usage:
    evaluation/.venv/bin/python evaluation/onboarding_trial.py
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BACKEND = "http://localhost:8170"
NEW_MODEL_NAME = "customer-churn-eu"
RESULTS_DIR = Path(__file__).parent / "results"


def _docker_exec_python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", "-i", "cmp_backend", "python", "-c", code],
                           capture_output=True, text=True, timeout=60)


ONBOARD_SNIPPET = """
import json
from app.database import SessionLocal
from app import models as m
from app import pipeline_engine as pe

db = SessionLocal()
model = m.TrainedModel(name="%(name)s", task_type="classification",
                        owner_team="retention-ml-eu", description="EU customer segment churn model (onboarding trial)")
db.add(model)
db.flush()
pe.ensure_sla_config(db)
run = pe.run_pipeline(db, model, trigger_type="manual", trigger_detail="Onboarding trial: initial training", scenario="healthy")
db.commit()
print(json.dumps({"model_id": model.id, "run_id": run.id, "run_status": run.status, "run_outcome": run.outcome}))
""" % {"name": NEW_MODEL_NAME}

CLEANUP_SNIPPET = """
from app.database import SessionLocal
from app import models as m

db = SessionLocal()
model = db.query(m.TrainedModel).filter_by(name="%(name)s").one_or_none()
if model:
    mid = model.id
    version_ids = [v.id for v in db.query(m.ModelVersion).filter_by(model_id=mid).all()]
    run_ids = [r.id for r in db.query(m.PipelineRun).filter_by(model_id=mid).all()]
    check_ids = [c.id for c in db.query(m.DriftCheck).filter_by(model_id=mid).all()]
    ds_ids = [d.id for d in db.query(m.DatasetVersion).filter_by(model_id=mid).all()]

    if check_ids:
        db.query(m.DriftFeatureResult).filter(m.DriftFeatureResult.drift_check_id.in_(check_ids)).delete(synchronize_session=False)
    db.query(m.DriftCheck).filter_by(model_id=mid).delete(synchronize_session=False)
    if version_ids:
        db.query(m.ProductionPrediction).filter(m.ProductionPrediction.model_version_id.in_(version_ids)).delete(synchronize_session=False)
        db.query(m.EvaluationResult).filter(m.EvaluationResult.candidate_version_id.in_(version_ids)).delete(synchronize_session=False)
        db.query(m.DeploymentEvent).filter(m.DeploymentEvent.model_version_id.in_(version_ids)).delete(synchronize_session=False)
        db.query(m.Alert).filter(m.Alert.model_version_id.in_(version_ids)).delete(synchronize_session=False)
    if run_ids:
        db.query(m.PipelineStage).filter(m.PipelineStage.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(m.SlaViolation).filter(m.SlaViolation.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(m.Alert).filter(m.Alert.run_id.in_(run_ids)).delete(synchronize_session=False)
    if ds_ids:
        db.query(m.DataQualityCheck).filter(m.DataQualityCheck.dataset_version_id.in_(ds_ids)).delete(synchronize_session=False)
        db.query(m.RawRecord).filter(m.RawRecord.dataset_version_id.in_(ds_ids)).delete(synchronize_session=False)
    db.query(m.ModelVersion).filter_by(model_id=mid).delete(synchronize_session=False)
    db.query(m.PipelineRun).filter_by(model_id=mid).delete(synchronize_session=False)
    db.query(m.DatasetVersion).filter_by(model_id=mid).delete(synchronize_session=False)
    db.query(m.AuditLog).filter(m.AuditLog.detail.like('%%onboarding trial%%')).delete(synchronize_session=False)
    db.delete(model)
    db.commit()
    print("cleaned up:", "%(name)s")
else:
    print("nothing to clean up")
""" % {"name": NEW_MODEL_NAME}


def main() -> None:
    assert requests.get(f"{BACKEND}/ready", timeout=5).json().get("ready"), "backend not ready"

    doc_log = [
        "Checked README.md (top-level project description, docker-compose usage) — no model-management section.",
        "Checked code/EVALUATION.md (harness usage) — describes evaluation tooling only, not model onboarding.",
        "Checked OpenAPI docs (GET /docs) route list — every write route takes an existing {model} path param "
        "(POST /{model}/training, /{model}/monitoring/check, /{model}/rollback); no POST /api/v1/models create route.",
        "Grepped backend/app/routers/*.py for @router.post|@router.put directly to confirm — 5 matches, none creates a model.",
        "Conclusion: onboarding a new model requires backend source/DB access (seed.py pattern), not a documented API call.",
    ]

    t_code_start = time.monotonic()
    proc = _docker_exec_python(ONBOARD_SNIPPET)
    t_code_done = time.monotonic()
    onboard_result = None
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            onboard_result = json.loads(proc.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            onboard_result = {"raw_stdout": proc.stdout.strip()}
    else:
        onboard_result = {"error": proc.stderr.strip()[-1000:]}

    verify = requests.get(f"{BACKEND}/api/v1/models", timeout=10).json()
    new_model_listed = any(mdl["name"] == NEW_MODEL_NAME for mdl in verify)

    check_resp = None
    if new_model_listed:
        check_resp = requests.post(
            f"{BACKEND}/api/v1/models/{NEW_MODEL_NAME}/monitoring/check",
            json={"profile": "stable", "auto_retrain": False}, timeout=30,
        ).json()

    cleanup_proc = _docker_exec_python(CLEANUP_SNIPPET)
    verify_after_cleanup = requests.get(f"{BACKEND}/api/v1/models", timeout=10).json()
    still_listed_after_cleanup = any(mdl["name"] == NEW_MODEL_NAME for mdl in verify_after_cleanup)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task": "Add a second monitored model, following only existing documentation, then verify + clean up",
        "step1_documentation_review": {
            "elapsed_seconds": None,
            "honesty_note": "Not measured. A genuine onboarding-lead-time duration requires a truly naive participant "
                             "who has not already worked with this codebase; the authors/agent producing this result "
                             "already know the codebase, so any duration claimed here would be fabricated, not measured. "
                             "Reported instead as a qualitative, independently-verifiable finding (see 'finding' below) "
                             "plus a real, task-based proxy: Step 2's mechanical DB-onboarding time.",
            "log": doc_log,
            "finding": "No documented/API path exists to add a model — every write endpoint requires an existing "
                       "model name; onboarding requires direct backend code/DB access (seed.py's own pattern).",
        },
        "step2_db_level_onboarding": {
            "elapsed_seconds": round(t_code_done - t_code_start, 3),
            "method": "docker exec into cmp_backend, reusing its own SQLAlchemy session + pipeline_engine.run_pipeline()",
            "result": onboard_result,
        },
        "step3_verification": {
            "new_model_listed_in_GET_models": new_model_listed,
            "independent_monitoring_check_result": check_resp,
        },
        "step4_cleanup": {
            "cleanup_stdout": cleanup_proc.stdout.strip(),
            "cleanup_stderr": cleanup_proc.stderr.strip()[-500:] if cleanup_proc.stderr else None,
            "model_still_listed_after_cleanup": still_listed_after_cleanup,
        },
        "total_elapsed_seconds": None,
        "total_elapsed_note": "Only Step 2's mechanical time is a real measurement (see above); no total is reported "
                              "since Step 1's duration was not honestly measurable in this session.",
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "onboarding_trial.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Create a dedicated kind model if it is missing (Paper B A/B/C n≥3).

There is no POST /api/v1/models route. This uses the same in-pod SQLAlchemy
path as onboarding_trial.py, but leaves the model in place.

Every kubectl call is pinned to kind-dact-local-eks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from k8s_runtime import BACKEND_URL, assert_kind_context, exec_python_in_backend


def _create_snippet(name: str) -> str:
    return f"""
import json
from app.database import SessionLocal
from app import models as m
from app import pipeline_engine as pe

db = SessionLocal()
existing = db.query(m.TrainedModel).filter_by(name={name!r}).one_or_none()
if existing:
    versions = db.query(m.ModelVersion).filter_by(model_id=existing.id).all()
    champ = next((v for v in versions if v.is_champion), None)
    print(json.dumps({{
        "created": False,
        "model_id": existing.id,
        "champion_version": champ.version if champ else None,
    }}))
else:
    model = m.TrainedModel(
        name={name!r},
        task_type="classification",
        owner_team="paper-b-eval",
        description="Dedicated Paper B A/B/C n>=3 model; do not use churn-predictor",
    )
    db.add(model)
    db.flush()
    pe.ensure_sla_config(db)
    run = pe.run_pipeline(
        db, model,
        trigger_type="manual",
        trigger_detail="Paper B seed healthy champion for paper-b-abc",
        scenario="healthy",
    )
    db.commit()
    print(json.dumps({{
        "created": True,
        "model_id": model.id,
        "run_id": run.id,
        "run_status": run.status,
        "run_outcome": run.outcome,
    }}))
"""


def ensure_kind_model(name: str) -> dict:
    assert_kind_context()
    ready = requests.get(f"{BACKEND_URL}/ready", timeout=5).json()
    if not ready.get("ready"):
        raise RuntimeError("kind backend is not ready")
    models = requests.get(f"{BACKEND_URL}/api/v1/models", timeout=10).json()
    listed = any(m.get("name") == name for m in models)
    if listed:
        versions = requests.get(f"{BACKEND_URL}/api/v1/models/{name}/versions", timeout=10).json()
        champ = next((v for v in versions if v.get("is_champion")), None)
        if champ:
            return {
                "name": name,
                "created": False,
                "already_present": True,
                "champion_version": champ.get("version"),
                "champion_f1": champ.get("test_f1"),
            }
    proc = exec_python_in_backend(_create_snippet(name), timeout=180)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ensure model failed")[-1500:])
    line = (proc.stdout or "").strip().splitlines()[-1]
    payload = json.loads(line)
    versions = requests.get(f"{BACKEND_URL}/api/v1/models/{name}/versions", timeout=10).json()
    champ = next((v for v in versions if v.get("is_champion")), None)
    payload.update({
        "name": name,
        "champion_version": champ.get("version") if champ else None,
        "champion_f1": champ.get("test_f1") if champ else None,
    })
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="paper-b-abc")
    args = parser.parse_args()
    report = ensure_kind_model(args.model)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

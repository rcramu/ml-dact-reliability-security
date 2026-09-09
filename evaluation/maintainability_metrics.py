#!/usr/bin/env python3
"""Maintainability metrics for the cmp_ reference stack (Paper B, Section 6.4).

Computes cyclomatic complexity (McCabe [13]) and lines-of-code per module via
`radon`, real static measurements against the actual backend/app and
airflow/dags source trees — not estimates.

Code churn (Nagappan & Ball [14]) requires commit history; this project has
no VCS (`git log` fails with "not a git repository"), so churn is reported as
unavailable rather than fabricated — see the honest-limitation note this
script prints and the corresponding note in the manuscript.

Onboarding lead time is a task-based, human-timed metric and is NOT computed
here — see evaluation/onboarding_protocol.md for the manual protocol.

Usage:
    evaluation/.venv/bin/python evaluation/maintainability_metrics.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_DIR = Path(__file__).parent / "results"
MODULES = {
    "backend/app/ml": PROJECT_ROOT / "backend/app/ml",
    "backend/app/routers": PROJECT_ROOT / "backend/app/routers",
    "backend/app/integrations": PROJECT_ROOT / "backend/app/integrations",
    "backend/app (top-level)": PROJECT_ROOT / "backend/app",
    "airflow/dags": PROJECT_ROOT / "airflow/dags",
}


def _radon(venv_python: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([venv_python, "-m", "radon", *args], capture_output=True, text=True)


def _check_git_history() -> dict:
    result = subprocess.run(["git", "-C", str(PROJECT_ROOT), "log", "--oneline", "-n", "1"],
                             capture_output=True, text=True)
    available = result.returncode == 0
    return {
        "available": available,
        "note": (
            "git history available" if available else
            "no VCS history in this project (`git log` failed: "
            f"{result.stderr.strip()!r}) — code churn (Nagappan & Ball, ref [14]) "
            "cannot be computed without commit history and is reported as N/A, "
            "not estimated. Cyclomatic complexity and LOC below do not depend on VCS history."
        ),
    }


def _complexity_for_module(venv_python: str, path: Path) -> dict | None:
    if not path.exists():
        return None
    py_files = [f for f in path.rglob("*.py") if "__pycache__" not in f.parts and ".venv" not in f.parts]
    if not py_files:
        return None
    cc = _radon(venv_python, "cc", "-s", "-j", str(path))
    raw = _radon(venv_python, "raw", "-j", str(path))
    try:
        cc_data = json.loads(cc.stdout)
    except json.JSONDecodeError:
        cc_data = {}
    try:
        raw_data = json.loads(raw.stdout)
    except json.JSONDecodeError:
        raw_data = {}

    complexities = []
    for _file, blocks in cc_data.items():
        for block in blocks:
            complexities.append(block["complexity"])
    total_loc = sum(v.get("loc", 0) for v in raw_data.values())
    total_lloc = sum(v.get("lloc", 0) for v in raw_data.values())

    return {
        "python_files": len(py_files),
        "functions_and_methods_measured": len(complexities),
        "avg_cyclomatic_complexity": round(sum(complexities) / len(complexities), 2) if complexities else None,
        "max_cyclomatic_complexity": max(complexities) if complexities else None,
        "total_loc": total_loc,
        "total_logical_loc": total_lloc,
    }


def main() -> None:
    venv_python = str(Path(__file__).parent / ".venv" / "bin" / "python")
    report = {
        "code_churn": _check_git_history(),
        "modules": {},
    }
    for label, path in MODULES.items():
        metrics = _complexity_for_module(venv_python, path)
        if metrics:
            report["modules"][label] = metrics

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "maintainability_metrics.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote {out_path}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

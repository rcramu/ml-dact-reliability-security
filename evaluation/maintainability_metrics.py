#!/usr/bin/env python3
"""Maintainability metrics for the Paper B deposit (Section 6.4).

Computes cyclomatic complexity (McCabe [13]) and lines-of-code per module via
`radon`, plus short-window Nagappan–Ball [14] churn over this repository's
git history (history starts at the archive commit).

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


def _churn_for_prefix(rel: str) -> dict:
    """Nagappan-Ball style added+deleted over the deposit git history."""
    proc = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "log", "--numstat", "--pretty=format:", "--", rel],
        capture_output=True,
        text=True,
    )
    added = deleted = 0
    files: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        if a == "-" or d == "-":
            continue
        added += int(a)
        deleted += int(d)
        files.add(path)
    return {
        "path": rel,
        "files_touched": len(files),
        "lines_added": added,
        "lines_deleted": deleted,
        "churn": added + deleted,
    }


def _check_git_history() -> dict:
    result = subprocess.run(["git", "-C", str(PROJECT_ROOT), "log", "--oneline"],
                             capture_output=True, text=True)
    available = result.returncode == 0 and bool(result.stdout.strip())
    commits = [line for line in result.stdout.splitlines() if line.strip()] if available else []
    prefixes = [
        "backend/app/ml",
        "backend/app/routers",
        "backend/app/integrations",
        "airflow/dags",
        "evaluation",
    ]
    by_module = {p: _churn_for_prefix(p) for p in prefixes} if available else {}
    return {
        "available": available,
        "commit_count": len(commits),
        "commits": commits[:20],
        "by_module": by_module,
        "note": (
            "Short-window churn on this public deposit only (history starts at the "
            "archive commit). Not a multi-year industrial churn study."
            if available else
            "no VCS history — code churn reported as N/A, not estimated."
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

#!/usr/bin/env python3
"""Recount Table 3 candidates under an F1-only / aggregate-regression gate.

Does not retrain. Reads captured A/B/C JSON and asks: would each candidate
have passed if the only check were F1-regression <= 0 (candidate F1 >= champion F1)?
The live multi-metric gate rejected all 9 Compose-window candidates on recall.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

RESULTS = Path(__file__).parent / "results"

COMPOSE_FILES = [
    RESULTS / "approach_comparison_stable.json",
    RESULTS / "approach_comparison_drifted.json",
    RESULTS / "approach_comparison_severe_drift.json",
]
KIND_FILES = [
    RESULTS / "approach_comparison_stable_kind.json",
    RESULTS / "approach_comparison_drifted_kind.json",
    RESULTS / "approach_comparison_severe_drift_kind.json",
]


def _candidate(block: dict) -> dict:
    if block.get("candidate_test_f1") is not None:
        return block
    return block.get("supplementary_forced_outcome") or {}


def _row(profile: str, approach_key: str, block: dict) -> dict:
    cand = _candidate(block)
    f1 = cand.get("candidate_test_f1")
    champ = cand.get("production_f1_after")
    reasons = cand.get("gate_reasons") or block.get("gate_reasons")
    reg = cand.get("gate_regression_pct")
    f1_only_pass = None
    if f1 is not None and champ is not None:
        f1_only_pass = float(f1) >= float(champ)
    return {
        "profile": profile,
        "approach": block.get("approach") or approach_key,
        "candidate_test_f1": f1,
        "champion_f1": champ,
        "gate_regression_pct": reg,
        "gate_reasons": reasons,
        "live_gate_promoted": bool(cand.get("promoted") or block.get("promoted")),
        "f1_only_would_pass": f1_only_pass,
    }


def recount(files: list[Path]) -> list[dict]:
    rows = []
    for path in files:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        profile = data.get("profile") or path.stem
        for key in ("approach_a", "approach_b", "approach_c"):
            if key in data:
                rows.append(_row(profile, key, data[key]))
    return rows


def summarize(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["f1_only_would_pass"] is not None]
    return {
        "n_candidates": len(scored),
        "live_gate_promoted_count": sum(1 for r in scored if r["live_gate_promoted"]),
        "f1_only_would_pass_count": sum(1 for r in scored if r["f1_only_would_pass"]),
        "f1_only_would_fail_count": sum(1 for r in scored if r["f1_only_would_pass"] is False),
        "rows": rows,
    }


def main() -> None:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rule": "F1-only pass iff candidate_test_f1 >= champion_f1 (equivalently gate_regression_pct <= 0)",
        "compose_window": summarize(recount(COMPOSE_FILES)),
        "kind_window": summarize(recount(KIND_FILES)),
    }
    out = RESULTS / "f1_only_ablation.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

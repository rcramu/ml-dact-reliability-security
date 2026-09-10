#!/usr/bin/env python3
"""Generate result figures from captured JSON (Paper B, Section 8/9).

Kind-window files are the primary Table 1 / Table 3 figures. Compose files
remain available as a second window.

Usage:
    evaluation/.venv/bin/python evaluation/make_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent.parent / "figures"


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def figure_mttr_kind(fault_data: dict) -> None:
    scenarios = fault_data["scenarios"]
    labels, values, notes, colors = [], [], [], []

    backend = scenarios["backend_kill_inflight"]
    auto = backend.get("auto_restart_mttr_seconds_avg")
    labels.append("Backend pod kill\n(auto /ready in 30 s)")
    values.append(auto if auto is not None else 0.0)
    n_ok = 5 - int(backend.get("manual_intervention_required_count") or 0)
    notes.append(f"{n_ok}/5 within bound")
    colors.append("#c0392b")

    mlflow = scenarios["mlflow_outage"]
    restores = [t.get("restore_elapsed_s") for t in mlflow.get("trials", []) if t.get("restore_elapsed_s") is not None]
    labels.append("MLflow scale-to-0\n(restore)")
    values.append(_avg(restores) or mlflow.get("mttr_seconds_avg") or 0.0)
    notes.append("train hung ≥45 s")
    colors.append("#e67e22")

    labels.append("MinIO\n(not on kind)")
    values.append(0.0)
    notes.append("N/A — MLflow PVC")
    colors.append("#95a5a6")

    rollback = scenarios["rollback_mechanism"]
    labels.append("Rollback call\n(v7→v1)")
    values.append(rollback["rollback_call_latency_seconds"])
    notes.append("restored correctly")
    colors.append("#27ae60")

    tick_labels = [f"{lab}\n{note}" for lab, note in zip(labels, notes)]
    fig, ax = plt.subplots(figsize=(7.4, 5.0))
    bars = ax.bar(tick_labels, values, color=colors)
    ymax = max(values) if max(values) > 0 else 1
    for bar, val, note in zip(bars, values, notes):
        label = "N/A" if val == 0 and "N/A" in note else f"{val:.2f}s"
        ax.text(bar.get_x() + bar.get_width() / 2, val + ymax * 0.03,
                 label, ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("Seconds")
    ax.set_title("Table 1 — Kind window recovery times (fault_injection_kind.json)")
    ax.set_ylim(0, ymax * 1.25)
    fig.tight_layout()
    FIGURES_DIR.mkdir(exist_ok=True)
    out = FIGURES_DIR / "figure1_reliability_mttr.png"
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


def _c_detection(block: dict) -> float:
    if block.get("triggered_retrain_live"):
        return float(block.get("total_call_latency_seconds") or 0)
    return float(block.get("total_call_latency_seconds") or block.get("detection_time_seconds_measured") or 0)


def _c_recovery(block: dict) -> float:
    if block.get("recovery_time_seconds") is not None:
        return float(block["recovery_time_seconds"])
    return float(block.get("supplementary_forced_recovery_time_seconds") or 0)


def figure_abc_kind(comparison_data: dict) -> None:
    approaches = ["A - Manual", "B - Scheduled", "C - Closed-loop"]
    detection = [
        comparison_data["approach_a"]["detection_time_seconds_measured"],
        None,
        _c_detection(comparison_data["approach_c"]),
    ]
    recovery = [
        comparison_data["approach_a"]["recovery_time_seconds"],
        comparison_data["approach_b"]["recovery_time_seconds"],
        _c_recovery(comparison_data["approach_c"]),
    ]
    c_live = bool(comparison_data["approach_c"].get("triggered_retrain_live"))

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    x = range(len(approaches))
    width = 0.35
    det_plot = [d if d is not None else 0 for d in detection]
    ax.bar([i - width / 2 for i in x], det_plot, width, label="Detection time (measured)", color="#2980b9")
    ax.bar([i + width / 2 for i in x], recovery, width, label="Recovery time (pipeline)", color="#8e44ad")
    ymax = max([v for v in det_plot + recovery if v is not None] or [1])
    for i, (d, r) in enumerate(zip(detection, recovery)):
        if d is None:
            ax.text(i - width / 2, ymax * 0.08, "analytical\n3.5 days", ha="center", va="bottom", fontsize=7, style="italic", color="#555")
            ax.text(i + width / 2, r + ymax * 0.03, f"{r:.1f}s", ha="center", fontsize=8, fontweight="bold")
        elif r is not None and abs(d - r) < 0.2:
            ax.text(i, r + ymax * 0.04, f"{d:.2f}s detect+recover" + (" (live)" if i == 2 and c_live else ""),
                    ha="center", fontsize=8, fontweight="bold")
        else:
            ax.text(i - width / 2, d + ymax * 0.03, f"{d:.2f}s", ha="center", fontsize=8, fontweight="bold")
            ax.text(i + width / 2, r + ymax * 0.03, f"{r:.1f}s", ha="center", fontsize=8, fontweight="bold")
            if i == 2 and c_live:
                ax.text(i + width / 2, r + ymax * 0.10, "live fire", ha="center", fontsize=7, style="italic")
    ax.set_xticks(list(x))
    ax.set_xticklabels(approaches)
    ax.set_ylabel("Seconds")
    ax.set_ylim(0, ymax * 1.28)
    scenario = comparison_data.get("scenario") or comparison_data.get("profile")
    ax.set_title(f"Table 3 — Kind A/B/C ({scenario})")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    out = FIGURES_DIR / "figure2_abc_comparison.png"
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


def figure_kind_matrix() -> None:
    """3×3 kind-window gate outcomes from the published Table 3 JSON (n=1 per cell)."""
    profiles = [
        ("stable", "healthy"),
        ("drifted", "feature_drift"),
        ("severe_drift", "regression"),
    ]
    approaches = [("approach_a", "A"), ("approach_b", "B"), ("approach_c", "C")]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.set_xlim(-0.5, 2.5)
    ax.set_ylim(-0.5, 2.5)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["A manual", "B scheduled", "C closed-loop"])
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["regression", "feature_drift", "healthy"])
    ax.set_title("Table 3 — Kind 3×3 gate outcomes (n=1 per cell)")
    for row, (profile, scenario) in enumerate(reversed(profiles)):
        path = RESULTS_DIR / f"approach_comparison_{profile}_kind.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for col, (key, _label) in enumerate(approaches):
            block = data[key]
            raw = (block.get("pipeline_outcome") or "n/a").upper()
            if raw in {"MODEL_NOT_PROMOTED", "REJECTED"}:
                outcome = "REJECTED"
            elif raw == "PROMOTED":
                outcome = "PROMOTED"
            else:
                outcome = raw
            live = bool(block.get("triggered_retrain_live"))
            if outcome == "PROMOTED":
                face = "#c8e6c9"
            elif key == "approach_c" and not live:
                face = "#fff3cd"
                outcome = "HOLD"
            else:
                face = "#ffcdd2"
            ax.add_patch(plt.Rectangle((col - 0.45, row - 0.45), 0.9, 0.9, facecolor=face, edgecolor="#333"))
            ax.text(col, row + 0.08, outcome, ha="center", va="center", fontsize=9, fontweight="bold")
            f1 = block.get("candidate_test_f1")
            if f1 is not None:
                ax.text(col, row - 0.22, f"F1 {f1:.3f}", ha="center", va="center", fontsize=7, color="#333")
    ax.set_aspect("equal")
    fig.tight_layout()
    FIGURES_DIR.mkdir(exist_ok=True)
    out = FIGURES_DIR / "figure6_kind_design_matrix.png"
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


def main() -> None:
    kind_fault = RESULTS_DIR / "fault_injection_kind.json"
    kind_abc = RESULTS_DIR / "approach_comparison_drifted_kind.json"
    if kind_fault.exists():
        figure_mttr_kind(json.loads(kind_fault.read_text()))
    else:
        print("skip kind MTTR: no fault_injection_kind.json")
    if kind_abc.exists():
        figure_abc_kind(json.loads(kind_abc.read_text()))
    else:
        print("skip kind A/B/C: no approach_comparison_drifted_kind.json")
    figure_kind_matrix()


if __name__ == "__main__":
    main()

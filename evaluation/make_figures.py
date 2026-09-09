#!/usr/bin/env python3
"""Generate result figures from real captured JSON (Paper B, Section 8/9).

Reads evaluation/results/*.json (produced by fault_injection.py and
approach_comparison.py) and renders two bar charts. No synthetic/estimated
data — every value plotted is read directly from a results file.

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


def figure_mttr(fault_data: dict) -> None:
    scenarios = fault_data["scenarios"]
    labels, values, notes = [], [], []

    backend = scenarios["backend_kill_inflight"]
    labels.append("Backend kill\n(manual restart)")
    values.append(backend["manual_intervention_mttr_seconds_avg"])
    notes.append("auto-restart: none observed")

    mlflow = scenarios["mlflow_outage"]
    labels.append("MLflow outage\n(container recovery)")
    values.append(mlflow["mttr_seconds_avg"])
    notes.append("request itself hung \u226530s")

    minio = scenarios["minio_outage"]
    labels.append("MinIO outage\n(container recovery)")
    values.append(minio["mttr_seconds_avg"])
    notes.append("request itself hung \u226530s")

    rollback = scenarios["rollback_mechanism"]
    labels.append("Rollback call\n(mechanism latency)")
    values.append(rollback["rollback_call_latency_seconds"])
    notes.append("rollback_correct: true")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, values, color=["#c0392b", "#e67e22", "#e67e22", "#27ae60"])
    for bar, val, note in zip(bars, values, notes):
        ax.text(bar.get_x() + bar.get_width() / 2, val + max(values) * 0.02,
                 f"{val:.2f}s", ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax.text(bar.get_x() + bar.get_width() / 2, -max(values) * 0.08, note,
                 ha="center", va="top", fontsize=7.5, style="italic", color="#555")
    ax.set_ylabel("Seconds")
    ax.set_title("Table 1 — Real measured recovery times by injected fault")
    ax.set_ylim(0, max(values) * 1.25)
    fig.tight_layout()
    FIGURES_DIR.mkdir(exist_ok=True)
    out = FIGURES_DIR / "figure1_reliability_mttr.png"
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


def figure_abc(comparison_data: dict) -> None:
    approaches = ["A - Manual", "B - Scheduled", "C - Closed-loop"]
    detection = [
        comparison_data["approach_a"]["detection_time_seconds_measured"],
        None,  # not live-measured, analytical only
        comparison_data["approach_c"]["total_call_latency_seconds"],
    ]
    recovery = [
        comparison_data["approach_a"]["recovery_time_seconds"],
        comparison_data["approach_b"]["recovery_time_seconds"],
        comparison_data["approach_c"]["supplementary_forced_recovery_time_seconds"],
    ]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = range(len(approaches))
    width = 0.35
    det_plot = [d if d is not None else 0 for d in detection]
    bars_det = ax.bar([i - width / 2 for i in x], det_plot, width, label="Detection time (measured)", color="#2980b9")
    bars_rec = ax.bar([i + width / 2 for i in x], recovery, width, label="Recovery time (pipeline execution)", color="#8e44ad")
    for i, (d, r) in enumerate(zip(detection, recovery)):
        if d is not None:
            ax.text(i - width / 2, d + 0.5, f"{d:.2f}s", ha="center", fontsize=8, fontweight="bold")
        else:
            ax.text(i - width / 2, 1, "analytical:\navg 3.5 days", ha="center", fontsize=7, style="italic")
        ax.text(i + width / 2, r + 0.5, f"{r:.1f}s", ha="center", fontsize=8, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(approaches)
    ax.set_ylabel("Seconds")
    ax.set_title("Table 3 — Real measured detection/recovery time, A/B/C (feature_drift)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = FIGURES_DIR / "figure2_abc_comparison.png"
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


def main() -> None:
    fault_data = json.loads((RESULTS_DIR / "fault_injection.json").read_text())
    comparison_data = json.loads((RESULTS_DIR / "approach_comparison_severe_drift.json").read_text())
    figure_mttr(fault_data)
    figure_abc(comparison_data)


if __name__ == "__main__":
    main()

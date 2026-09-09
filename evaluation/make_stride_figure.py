#!/usr/bin/env python3
"""Figure 5: STRIDE trust-boundary severity map (Paper B, Section 6.3/Table 2).

Real data transcribed directly from evaluation/threat_model.md's finding
table (7 trust boundaries, each with a manually-assessed severity) — nothing
synthetic, this just visualizes the existing table.

Usage:
    evaluation/.venv/bin/python evaluation/make_stride_figure.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURES_DIR = Path(__file__).parent.parent / "figures"

# (trust boundary, STRIDE categories, severity) — transcribed from threat_model.md
BOUNDARIES = [
    ("External client \u2192 cmp_backend (8170)", "Tampering / DoS", "High"),
    ("Airflow webserver (8770)", "Spoofing / Elevation", "High"),
    ("cmp_backend \u2192 cmp_mlflow", "Tampering", "Medium"),
    ("cmp_backend \u2192 cmp_minio", "Info. disclosure / Tampering", "Medium"),
    ("Grafana (3370)", "Spoofing / Info. disclosure", "High"),
    ("Splunk HEC (8371)", "Tampering", "Medium"),
    ("write_to_s3 / log_mlflow stages", "Repudiation / Tampering", "High (integrity)"),
    ("Rollback endpoint", "Elevation of privilege", "High"),
]

SEVERITY_COLOR = {"High": "#c0392b", "High (integrity)": "#8e44ad", "Medium": "#e67e22"}
SEVERITY_RANK = {"High": 3, "High (integrity)": 3, "Medium": 2}


def main() -> None:
    labels = [b[0] for b in BOUNDARIES]
    cats = [b[1] for b in BOUNDARIES]
    sevs = [b[2] for b in BOUNDARIES]
    ranks = [SEVERITY_RANK[s] for s in sevs]
    colors = [SEVERITY_COLOR[s] for s in sevs]

    fig, ax = plt.subplots(figsize=(8, 5))
    y = range(len(labels))
    ax.barh(y, ranks, color=colors)
    for i, (cat, sev) in enumerate(zip(cats, sevs)):
        ax.text(ranks[i] + 0.05, i, f"{sev} \u2014 {cat}", va="center", fontsize=8)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_xticks([])
    ax.set_xlim(0, 6.5)
    ax.invert_yaxis()
    ax.set_title("Figure 5 — STRIDE trust-boundary findings (5 of 7 rated High)\nreal findings, evaluation/threat_model.md")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in ["#c0392b", "#8e44ad", "#e67e22"]]
    ax.legend(handles, ["High", "High (integrity)", "Medium"], loc="upper right", fontsize=8, framealpha=0.95)
    fig.tight_layout()
    FIGURES_DIR.mkdir(exist_ok=True)
    out = FIGURES_DIR / "figure4_stride_severity.png"
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compose the JSS graphical abstract from measured paper numbers (no generative art)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT_DIR = Path(__file__).resolve().parent.parent / "figures"
SUBMISSION_DIR = Path(__file__).resolve().parents[2] / "jss-submission"


def _panel(ax, title: str, bullets: list[str], face: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(
        FancyBboxPatch(
            (0.03, 0.06),
            0.94,
            0.88,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            linewidth=1.2,
            edgecolor="#1f3a5f",
            facecolor=face,
        )
    )
    ax.text(0.08, 0.82, title, fontsize=13, fontweight="bold", color="#102a43", va="center")
    y = 0.62
    for line in bullets:
        ax.text(0.08, y, line, fontsize=10, color="#243b53", va="center")
        y -= 0.16


def main() -> None:
    # JSS: 531 x 1328 px (h x w) or proportionally more.
    fig = plt.figure(figsize=(13.28, 5.31), dpi=200)
    fig.patch.set_facecolor("white")
    fig.text(
        0.5,
        0.94,
        "Empirical reliability and security of drift-aware continuous training",
        ha="center",
        va="center",
        fontsize=15,
        fontweight="bold",
        color="#102a43",
    )
    fig.text(
        0.5,
        0.87,
        "Companion to JSSOFTWARE-D-26-02282  ·  kind dact-local-eks + Compose window  ·  measured",
        ha="center",
        va="center",
        fontsize=9,
        color="#486581",
    )

    gs = fig.add_gridspec(1, 3, left=0.03, right=0.97, bottom=0.08, top=0.80, wspace=0.04)
    _panel(
        fig.add_subplot(gs[0, 0]),
        "Reliability  (kind, n=5)",
        [
            "Backend pod: 1/5 /ready in 30 s",
            "MLflow down: train hung ≥45 s",
            "MinIO not deployed on kind",
            "Rollback v7→v1 in 0.76 s",
        ],
        "#e3f0ff",
    )
    _panel(
        fig.add_subplot(gs[0, 1]),
        "Security  (scan + STRIDE)",
        [
            "86 OSV advisories / 18 pins",
            "10 credential / port findings",
            "5 of 7 High STRIDE boundaries",
            "Silent MLflow fail confirmed live",
        ],
        "#fff4e0",
    )
    _panel(
        fig.add_subplot(gs[0, 2]),
        "A/B/C  (kind, 9 runs)",
        [
            "C fired on feature_drift",
            "C held on healthy / regression",
            "B waits avg 3.5 scheduled days",
            "Compose: 0/9 pass; F1-only 6/9",
        ],
        "#e7f6ee",
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / "graphical-abstract.png"
    pdf = OUT_DIR / "graphical-abstract.pdf"
    fig.savefig(png, dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf, dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(SUBMISSION_DIR / "graphical-abstract.png", dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(SUBMISSION_DIR / "graphical-abstract.pdf", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {png} and {pdf}")


if __name__ == "__main__":
    main()

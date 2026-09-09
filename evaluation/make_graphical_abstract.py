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
        "Reliability and security evaluation of a closed-loop MLOps stack",
        ha="center",
        va="center",
        fontsize=15,
        fontweight="bold",
        color="#102a43",
    )
    fig.text(
        0.5,
        0.87,
        "Companion to JSSOFTWARE-D-26-02282  ·  Compose snapshot  ·  measured, not estimated",
        ha="center",
        va="center",
        fontsize=9,
        color="#486581",
    )

    gs = fig.add_gridspec(1, 3, left=0.03, right=0.97, bottom=0.08, top=0.80, wspace=0.04)
    _panel(
        fig.add_subplot(gs[0, 0]),
        "Reliability  (n=5 faults)",
        [
            "Backend kill: no self-heal",
            "Manual start 3.69 ± 1.09 s",
            "MLflow / MinIO: hang ≥30 s",
            "Rollback restored prior champion",
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
        "A/B/C  (9 live runs)",
        [
            "C / A detect in seconds",
            "B waits avg 3.5 scheduled days",
            "Gate rejected 9/9 on recall",
            "C never auto-fired (GOOD eval)",
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

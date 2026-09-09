#!/usr/bin/env python3
"""Figure 8: orphaned-transaction cascade timeline (Paper B, Section 10 RQ1).

Real timestamps captured live during this study via:
    SELECT pid, state, now() - query_start AS held_for, query
    FROM pg_stat_activity WHERE state='idle in transaction';
(see the session transcript / repo memory note for the raw psql output —
this script only re-derives the x-axis offsets from those real timestamps,
nothing here is synthetic).

Usage:
    evaluation/.venv/bin/python evaluation/make_cascade_figure.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURES_DIR = Path(__file__).parent.parent / "figures"

# (pid, query_start, terminated_at) — all real, from the live pg_stat_activity
# query and the pg_terminate_backend call that followed it in this session.
FMT = "%H:%M:%S"
TERMINATED_AT = datetime.strptime("04:35:15", FMT)
TRIALS = [
    ("61014", "04:22:12"),
    ("61365", "04:22:55"),
    ("61119", "04:23:28"),
    ("61419", "04:24:06"),
    ("61520", "04:27:42"),
    ("61877", "04:29:27"),
    ("62042", "04:31:46"),
]
# The real new-request timeout observed immediately after these accumulated
# (client-side ReadTimeout at 60s, then 120s, then a request that never
# returned within a 200s curl -m 200 probe).
NEW_REQUEST_ATTEMPTS = [
    ("stable-profile retry #1", "04:33:00", 60),
    ("stable-profile retry #2", "04:34:00", 120),
    ("direct curl probe", "04:35:00", 200),
]


def main() -> None:
    t0 = min(datetime.strptime(t, FMT) for _, t in TRIALS)

    fig, ax = plt.subplots(figsize=(8, 5))

    for i, (pid, start) in enumerate(TRIALS):
        t_start = (datetime.strptime(start, FMT) - t0).total_seconds() / 60
        t_end = (TERMINATED_AT - t0).total_seconds() / 60
        ax.barh(i, t_end - t_start, left=t_start, height=0.6, color="#c0392b", alpha=0.85)
        ax.text(t_start - 0.3, i, f"pid {pid}", ha="right", va="center", fontsize=8)

    base_y = len(TRIALS) + 0.8
    for j, (label, start, dur_s) in enumerate(NEW_REQUEST_ATTEMPTS):
        t_start = (datetime.strptime(start, FMT) - t0).total_seconds() / 60
        dur_min = dur_s / 60
        y = base_y + j
        ax.barh(y, dur_min, left=t_start, height=0.5, color="#2980b9", alpha=0.85)
        ax.text(t_start - 0.3, y, label, ha="right", va="center", fontsize=8)
        ax.text(t_start + dur_min + 0.2, y, f"blocked {dur_s}s", ha="left", va="center",
                fontsize=7.5, style="italic", color="#555")

    ax.axvline((TERMINATED_AT - t0).total_seconds() / 60, color="#27ae60", linestyle="--", linewidth=1.5)
    ax.text((TERMINATED_AT - t0).total_seconds() / 60 + 0.3, base_y - 0.7,
            "pg_terminate_backend()\n+ cmp_backend restart\n\u2192 immediate recovery",
            fontsize=7.5, color="#27ae60", va="top", ha="left")

    ax.set_ylim(-0.8, base_y + len(NEW_REQUEST_ATTEMPTS) + 0.8)
    ax.set_yticks([])
    ax.set_xlabel("Minutes since first orphaned transaction (real timestamps, this session)")
    ax.set_title("Figure 8 — Orphaned-transaction cascade: 7 stuck sessions (red)\nblock 3 new requests (blue) until manual intervention (green)")
    fig.tight_layout()
    FIGURES_DIR.mkdir(exist_ok=True)
    out = FIGURES_DIR / "figure3_orphaned_transaction_cascade.png"
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

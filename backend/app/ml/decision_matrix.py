"""The drift + evaluation decision matrix (req.md Sec. 12-13) — the platform's key
design principle: drift alone does not indicate model failure, so every monitoring
run's final status combines BOTH signals rather than treating any single statistic
as the verdict.
"""

# (drift_level, evaluation_level) -> (overall_status, recommended_action)
DECISION_MATRIX = {
    ("LOW", "GOOD"): ("GREEN", "Continue"),
    ("HIGH", "GOOD"): ("WARNING", "Investigate"),
    ("LOW", "BAD"): ("CRITICAL", "Investigate model"),
    ("HIGH", "BAD"): ("CRITICAL", "Retrain/review"),
    ("HIGH", "UNKNOWN"): ("WARNING", "Obtain ground truth"),
    ("LOW", "UNKNOWN"): ("NORMAL", "Continue monitoring"),
}


def decide(drift_level: str, evaluation_level: str) -> tuple[str, str]:
    return DECISION_MATRIX.get((drift_level, evaluation_level), ("WARNING", "Investigate"))


def should_retrain(drift_level: str, evaluation_level: str) -> bool:
    """req.md Sec. 13 — automatic retraining trigger: only when drift is HIGH AND the
    model's evaluated quality is not confirmed GOOD (BAD or UNKNOWN)."""
    return drift_level == "HIGH" and evaluation_level != "GOOD"

"""Deterministic synthetic customer-churn data generator (req.md Sec. 1, 12-14 pattern).

Features model a typical telecom/subscription churn dataset: tenure, monthly
charges, age, support tickets, weekly usage, contract type, payment method,
and add-on services. Every scenario accepts a deterministic seed so
`docker compose up` always reproduces the exact same ingested data and
training outcomes (see repo-wide hash()-determinism gotcha — always seed via
sha256, never Python's randomized builtin hash()).
"""
import numpy as np

FEATURE_NAMES = [
    "tenure_months", "monthly_charges", "age", "support_tickets_90d",
    "usage_hours_week", "is_month_to_month", "autopay_enabled", "has_addons",
]

# True underlying weights used to synthesize `churn` — kept private to the
# generator; the model must LEARN these from data, never see them directly.
# Empirically validated (see session notes) to land the "healthy" scenario's
# churn rate around ~24%, a realistic subscription-churn baseline.
_TRUE_WEIGHTS = np.array([-1.4, 0.6, -0.1, 1.3, -0.9, 1.6, -0.7, -0.5])
_BIAS = -2.3


def stable_seed(key: str) -> int:
    import hashlib
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**31)


def _raw_features(rng: np.random.Generator, n: int) -> dict:
    tenure_months = np.clip(rng.exponential(24, n), 1, 72)
    monthly_charges = np.clip(rng.normal(70, 25, n), 20, 150)
    age = np.clip(rng.normal(42, 14, n), 18, 85)
    support_tickets_90d = rng.poisson(1.1, n)
    usage_hours_week = np.clip(rng.normal(12, 6, n), 0, 40)
    is_month_to_month = (rng.random(n) < 0.45).astype(int)
    autopay_enabled = (rng.random(n) < 0.55).astype(int)
    has_addons = (rng.random(n) < 0.35).astype(int)
    return {
        "tenure_months": tenure_months, "monthly_charges": monthly_charges, "age": age,
        "support_tickets_90d": support_tickets_90d, "usage_hours_week": usage_hours_week,
        "is_month_to_month": is_month_to_month, "autopay_enabled": autopay_enabled,
        "has_addons": has_addons,
    }


def _standardize(features: dict) -> np.ndarray:
    return np.stack([
        (features["tenure_months"] - 24) / 18,
        (features["monthly_charges"] - 70) / 25,
        (features["age"] - 42) / 14,
        (features["support_tickets_90d"] - 1.1) / 1.1,
        (features["usage_hours_week"] - 12) / 6,
        features["is_month_to_month"].astype(float),
        features["autopay_enabled"].astype(float),
        features["has_addons"].astype(float),
    ], axis=1)


def _labels_from_features(rng: np.random.Generator, x: np.ndarray, noise_sigma: float) -> np.ndarray:
    logit = x @ _TRUE_WEIGHTS + _BIAS + rng.normal(0, noise_sigma, x.shape[0])
    p = 1 / (1 + np.exp(-logit))
    return (rng.random(x.shape[0]) < p).astype(int)


def generate_scenario(scenario: str, seed: int, expected_rows: int = 1200) -> list[dict]:
    """Returns a list of raw record dicts (features + label + split)."""
    rng = np.random.default_rng(seed)
    n = expected_rows

    if scenario == "volume_anomaly":
        n = max(40, int(expected_rows * 0.12))  # ingestion job only delivered ~12% of expected rows
    elif scenario == "label_imbalance":
        n = expected_rows

    features = _raw_features(rng, n)

    if scenario == "feature_drift":
        # Meaningful shift: rising support tickets + falling engagement (usage hours) —
        # a realistic "customers are getting frustrated and disengaging" narrative.
        features["support_tickets_90d"] = rng.poisson(2.6, n)
        features["usage_hours_week"] = np.clip(rng.normal(7, 5, n), 0, 40)

    x = _standardize(features)

    if scenario == "regression":
        labels = _labels_from_features(rng, x, noise_sigma=3.0)
    else:
        labels = _labels_from_features(rng, x, noise_sigma=0.35)

    if scenario == "label_imbalance":
        target_churn = max(2, int(n * 0.02))
        churn_idx = np.where(labels == 1)[0]
        healthy_idx = np.where(labels == 0)[0]
        if len(churn_idx) > target_churn:
            keep_churn = rng.choice(churn_idx, size=target_churn, replace=False)
        else:
            keep_churn = churn_idx
        target_healthy = n - len(keep_churn)
        if len(healthy_idx) < target_healthy:
            pad = rng.choice(healthy_idx, size=target_healthy - len(healthy_idx), replace=True)
            keep_healthy = np.concatenate([healthy_idx, pad])
        else:
            keep_healthy = rng.choice(healthy_idx, size=target_healthy, replace=False)
        keep = np.concatenate([keep_healthy, keep_churn])
        rng.shuffle(keep)
        for k in features:
            features[k] = features[k][keep]
        labels = labels[keep]
        n = len(keep)

    order = rng.permutation(n)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)
    splits = np.empty(n, dtype=object)
    splits[order[:train_end]] = "train"
    splits[order[train_end:val_end]] = "val"
    splits[order[val_end:]] = "test"

    records = []
    for i in range(n):
        records.append({
            "split": str(splits[i]),
            "tenure_months": int(features["tenure_months"][i]),
            "monthly_charges": round(float(features["monthly_charges"][i]), 2),
            "age": int(features["age"][i]),
            "support_tickets_90d": int(features["support_tickets_90d"][i]),
            "usage_hours_week": round(float(features["usage_hours_week"][i]), 2),
            "is_month_to_month": bool(features["is_month_to_month"][i]),
            "autopay_enabled": bool(features["autopay_enabled"][i]),
            "has_addons": bool(features["has_addons"][i]),
            "label": int(labels[i]),
        })
    return records


def records_to_arrays(records: list[dict], split: str | None = None):
    """Converts stored RawRecord-shaped dicts back into (X, y) numpy arrays for training/eval."""
    rows = [r for r in records if split is None or r["split"] == split]
    features = {
        "tenure_months": np.array([r["tenure_months"] for r in rows], dtype=float),
        "monthly_charges": np.array([r["monthly_charges"] for r in rows], dtype=float),
        "age": np.array([r["age"] for r in rows], dtype=float),
        "support_tickets_90d": np.array([r["support_tickets_90d"] for r in rows], dtype=float),
        "usage_hours_week": np.array([r["usage_hours_week"] for r in rows], dtype=float),
        "is_month_to_month": np.array([int(r["is_month_to_month"]) for r in rows], dtype=float),
        "autopay_enabled": np.array([int(r["autopay_enabled"]) for r in rows], dtype=float),
        "has_addons": np.array([int(r["has_addons"]) for r in rows], dtype=float),
    }
    x = np.stack([
        (features["tenure_months"] - 24) / 18,
        (features["monthly_charges"] - 70) / 25,
        (features["age"] - 42) / 14,
        (features["support_tickets_90d"] - 1.1) / 1.1,
        (features["usage_hours_week"] - 12) / 6,
        features["is_month_to_month"],
        features["autopay_enabled"],
        features["has_addons"],
    ], axis=1) if rows else np.zeros((0, 8))
    y = np.array([r["label"] for r in rows], dtype=int)
    return x, y


def generate_production_batch(profile: str, seed: int, n: int = 200) -> list[dict]:
    """Simulates a batch of live scoring requests hitting POST /predict (req.md Sec. 10-12).

    `profile` controls whether production traffic still resembles the training
    distribution ("stable") or has drifted ("drifted" / "severe_drift").
    """
    rng = np.random.default_rng(seed)
    features = _raw_features(rng, n)
    if profile in ("drifted", "severe_drift"):
        shift = 1.0 if profile == "drifted" else 1.9
        features["support_tickets_90d"] = rng.poisson(1.1 + 1.2 * shift, n)
        features["usage_hours_week"] = np.clip(rng.normal(12 - 4 * shift, 6, n), 0, 40)
        features["monthly_charges"] = np.clip(rng.normal(70 + 8 * shift, 25, n), 20, 150)
    x = _standardize(features)
    noise = 0.35 if profile == "stable" else (0.9 if profile == "drifted" else 1.6)
    labels = _labels_from_features(rng, x, noise_sigma=noise)
    records = []
    for i in range(n):
        records.append({
            "tenure_months": int(features["tenure_months"][i]),
            "monthly_charges": round(float(features["monthly_charges"][i]), 2),
            "age": int(features["age"][i]),
            "support_tickets_90d": int(features["support_tickets_90d"][i]),
            "usage_hours_week": round(float(features["usage_hours_week"][i]), 2),
            "is_month_to_month": bool(features["is_month_to_month"][i]),
            "autopay_enabled": bool(features["autopay_enabled"][i]),
            "has_addons": bool(features["has_addons"][i]),
            "ground_truth": int(labels[i]),
        })
    return records


def feature_matrix(records: list[dict]) -> dict:
    """Returns {feature_name: np.ndarray} for every FEATURE_NAMES column — used by
    drift detection to compare reference (training) vs production distributions."""
    return {
        "tenure_months": np.array([r["tenure_months"] for r in records], dtype=float),
        "monthly_charges": np.array([r["monthly_charges"] for r in records], dtype=float),
        "age": np.array([r["age"] for r in records], dtype=float),
        "support_tickets_90d": np.array([r["support_tickets_90d"] for r in records], dtype=float),
        "usage_hours_week": np.array([r["usage_hours_week"] for r in records], dtype=float),
        "is_month_to_month": np.array([float(r["is_month_to_month"]) for r in records]),
        "autopay_enabled": np.array([float(r["autopay_enabled"]) for r in records]),
        "has_addons": np.array([float(r["has_addons"]) for r in records]),
    }


def production_records_to_arrays(records: list[dict]):
    """Like records_to_arrays but for generate_production_batch()'s shape (no 'split',
    label key is 'ground_truth')."""
    features = feature_matrix(records)
    x = np.stack([
        (features["tenure_months"] - 24) / 18,
        (features["monthly_charges"] - 70) / 25,
        (features["age"] - 42) / 14,
        (features["support_tickets_90d"] - 1.1) / 1.1,
        (features["usage_hours_week"] - 12) / 6,
        features["is_month_to_month"],
        features["autopay_enabled"],
        features["has_addons"],
    ], axis=1) if records else np.zeros((0, 8))
    y = np.array([r.get("ground_truth", 0) for r in records], dtype=int)
    return x, y

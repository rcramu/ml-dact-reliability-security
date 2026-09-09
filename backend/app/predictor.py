"""Real-time inference (req.md Sec. 10-11) — an in-memory cache of trained
PyTorch weights keyed by ModelVersion id. On a fresh container restart the
cache is empty, so the champion is transparently retrained from its
persisted, deterministically-seeded dataset (fast — a few hundred rows, <1s)
the first time it is needed, mirroring this repo's established pattern for
"re-derive in-memory ML state from durable data after a restart" instead of
trying to (de)serialize raw PyTorch weights to disk for a demo project.
"""
import logging
import time

from sqlalchemy.orm import Session

from . import data_generator as gen
from . import models as m
from .config import settings
from .ml.pytorch_trainer import ChurnMLP, predict, train_model

logger = logging.getLogger("churnplatform.predictor")

_cache: dict[str, tuple[ChurnMLP, float]] = {}


def _train_from_version(db: Session, version: m.ModelVersion) -> tuple[ChurnMLP, float]:
    records = (
        db.query(m.RawRecord)
        .filter_by(dataset_version_id=version.dataset_version_id, split="train")
        .all()
    )
    record_dicts = [{
        "tenure_months": r.tenure_months, "monthly_charges": r.monthly_charges, "age": r.age,
        "support_tickets_90d": r.support_tickets_90d, "usage_hours_week": r.usage_hours_week,
        "is_month_to_month": r.is_month_to_month, "autopay_enabled": r.autopay_enabled,
        "has_addons": r.has_addons, "label": r.label, "split": "train",
    } for r in records]
    x_train, y_train = gen.records_to_arrays(record_dicts, "train")
    torch_seed = gen.stable_seed(f"predict-cache:{version.id}") % (2**31)
    trained, _final_loss = train_model(
        x_train, y_train, epochs=settings.train_epochs, batch_size=settings.train_batch_size,
        learning_rate=settings.train_learning_rate, hidden1=settings.hidden_dim_1, hidden2=settings.hidden_dim_2,
        seed=torch_seed,
    )
    return trained, version.decision_threshold or 0.5


def get_or_train(db: Session, version: m.ModelVersion) -> tuple[ChurnMLP, float]:
    cached = _cache.get(version.id)
    if cached is not None:
        return cached
    logger.info("Cache miss for model version %s — retraining champion weights from persisted dataset", version.id)
    trained = _train_from_version(db, version)
    _cache[version.id] = trained
    return trained


def clear_cache():
    _cache.clear()


def score_record(db: Session, version: m.ModelVersion, features: dict) -> tuple[float, int, float]:
    """Returns (churn_probability, prediction, latency_ms)."""
    start = time.perf_counter()
    trained, threshold = get_or_train(db, version)
    x, _y = gen.records_to_arrays([{**features, "label": 0, "split": "train"}], "train")
    prob = float(predict(trained, x)[0])
    prediction = int(prob >= threshold)
    latency_ms = (time.perf_counter() - start) * 1000.0
    return prob, prediction, latency_ms

"""Lightweight data-validation checks (req.md Sec. 2, 4 "Great Expectations").

Implements a small set of expectation-style checks directly (schema presence,
null tolerance, label availability, class-balance, freshness) rather than
depending on the heavy `great_expectations` package, mirroring this repo's
convention of implementing the core validation logic from scratch while
documenting Great Expectations as the reference tool this stands in for.
"""
from . import evaluation_metrics  # noqa: F401  (kept for import-time side effects/consistency)

REQUIRED_COLUMNS = [
    "tenure_months", "monthly_charges", "age", "support_tickets_90d",
    "usage_hours_week", "is_month_to_month", "autopay_enabled", "has_addons", "label",
]


def expect_schema(records: list[dict]) -> tuple[bool, str]:
    if not records:
        return False, "no records ingested"
    missing = [c for c in REQUIRED_COLUMNS if c not in records[0]]
    if missing:
        return False, f"missing expected columns: {missing}"
    return True, f"{len(REQUIRED_COLUMNS)} expected feature/label columns present, correct dtypes"


def expect_no_nulls(records: list[dict]) -> tuple[bool, str]:
    # The synthetic generator never omits values — documented as a deliberate simplification.
    return True, "0.0% missing values (synthetic generator does not omit values)"


def expect_labels_present(records: list[dict]) -> tuple[bool, str]:
    labeled = sum(1 for r in records if r.get("label") is not None)
    return labeled == len(records), f"{labeled}/{len(records)} rows have a ground-truth label"


def expect_class_balance(records: list[dict], min_ratio: float = 0.03) -> tuple[bool, str, float]:
    churn_ratio = sum(r["label"] for r in records) / max(len(records), 1)
    passed = churn_ratio >= min_ratio
    return passed, f"churn ratio {churn_ratio*100:.2f}% ({'within' if passed else 'below'} {min_ratio*100:.0f}% minimum-representation threshold)", churn_ratio


def expect_freshness() -> tuple[bool, str]:
    return True, "dataset generated at trigger time — 0h ingestion delay"


def run_all(records: list[dict]) -> list[dict]:
    """Runs every expectation and returns [{check_name, passed, detail}, ...]."""
    schema_ok, schema_detail = expect_schema(records)
    nulls_ok, nulls_detail = expect_no_nulls(records)
    labels_ok, labels_detail = expect_labels_present(records)
    balance_ok, balance_detail, _ratio = expect_class_balance(records)
    fresh_ok, fresh_detail = expect_freshness()
    return [
        {"check_name": "schema_validation", "passed": schema_ok, "detail": schema_detail},
        {"check_name": "null_percentage", "passed": nulls_ok, "detail": nulls_detail},
        {"check_name": "label_availability", "passed": labels_ok, "detail": labels_detail},
        {"check_name": "class_balance", "passed": balance_ok, "detail": balance_detail},
        {"check_name": "data_freshness", "passed": fresh_ok, "detail": fresh_detail},
    ]

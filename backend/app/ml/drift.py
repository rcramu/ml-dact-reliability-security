"""Statistical drift detection — PSI, KS test (req.md Sec. 12).

Implements PSI/KS from scratch (numpy/scipy) rather than depending on the
heavy Evidently package, mirroring this repo's convention of implementing the
core statistical method directly while documenting Evidently as the reference
implementation this stands in for.
"""
import numpy as np
from scipy import stats

_EPS = 1e-6


def psi_numeric(reference: np.ndarray, production: np.ndarray, bins: int = 10) -> float:
    """PSI = sum (Actual% - Expected%) x ln(Actual% / Expected%)."""
    if len(reference) == 0 or len(production) == 0:
        return 0.0
    quantiles = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(quantiles) < 3:
        return 0.0
    quantiles[0], quantiles[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(reference, bins=quantiles)
    prod_counts, _ = np.histogram(production, bins=quantiles)
    ref_pct = ref_counts / max(ref_counts.sum(), 1) + _EPS
    prod_pct = prod_counts / max(prod_counts.sum(), 1) + _EPS
    return float(np.sum((prod_pct - ref_pct) * np.log(prod_pct / ref_pct)))


def ks_test(reference: np.ndarray, production: np.ndarray) -> tuple[float, float]:
    """Kolmogorov-Smirnov test for numerical distributions."""
    if len(reference) < 2 or len(production) < 2:
        return 0.0, 1.0
    result = stats.ks_2samp(reference, production)
    return float(result.statistic), float(result.pvalue)


def feature_status(psi: float, psi_warning: float, psi_critical: float) -> str:
    """PSI classification bands: <0.10 GREEN, 0.10-0.25 WARNING, >0.25 CRITICAL."""
    if psi >= psi_critical:
        return "CRITICAL"
    if psi >= psi_warning:
        return "WARNING"
    return "GREEN"

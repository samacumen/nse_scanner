"""Ranking -> top N (blueprint 8.6).

Six metrics, NaN-safe z-scoring (B3), finite-guarded ATR momentum,
small-cohort guard, tie-break by liquidity then uncensored>censored.
"""
from __future__ import annotations

import math

import numpy as np

# Fixed in code (blueprint 6): tie-break = liquidity; small-cohort threshold = 3.
SMALL_COHORT_THRESHOLD = 3
_EPS = 1e-9

METRICS = [
    "momentum",
    "zone_confluence",
    "rsi_quality",
    "liquidity",
    "recency",
    "volume_expansion",
]


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def compute_metrics(rec: dict) -> dict:
    """Raw (higher = better) metrics for one flagged record."""
    atr14 = rec["atr14"]
    if not math.isfinite(atr14) or atr14 <= 0:  # finite-guarded denominator (8.1/8.6)
        atr14 = rec["last_close"] * 0.02
    momentum = (rec["h_recent"] - rec["h_prev"]) / atr14

    close_w = rec["band_close_w"]
    band_lo, band_hi, band_mid = rec["band_lo"], rec["band_hi"], rec["band_mid"]
    width = band_hi - band_lo
    tightness = _clamp(1.0 - (width / close_w if close_w else 0.0), -1.0, 1.0)
    centering = _clamp(
        1.0 - abs(close_w - band_mid) / (width / 2.0 + _EPS), -1.0, 1.0
    )
    zone_confluence = 0.5 * tightness + 0.5 * centering

    liquidity = math.log10(rec["liquidity"]) if rec["liquidity"] > 0 else float("nan")
    recency = 1.0 - rec["bars_since_recent"] / rec["lookback_days"]  # fresher = higher (ranking only)
    vol_med = rec["vol_median20"]
    volume_expansion = (rec["vol_recent"] / vol_med) if vol_med and vol_med > 0 else float("nan")

    return {
        "momentum": momentum,
        "zone_confluence": zone_confluence,
        "rsi_quality": rec["rsi_trough"],
        "liquidity": liquidity,
        "recency": recency,
        "volume_expansion": volume_expansion,
    }


def _nan_z(values):
    """NaN-safe z-scores. NaN imputes to cohort mean -> contributes 0.
    Returns zeros (skip) if n < threshold or std == 0."""
    arr = np.array(values, dtype=float)
    n = np.sum(~np.isnan(arr))
    if n < SMALL_COHORT_THRESHOLD:
        return np.zeros(len(arr))
    mean = np.nanmean(arr)
    std = np.nanstd(arr)
    if not np.isfinite(std) or std == 0:
        return np.zeros(len(arr))
    filled = np.where(np.isnan(arr), mean, arr)  # NaN -> mean -> z=0
    return (filled - mean) / std


def rank(records: list, cfg) -> list:
    """Attach metrics/score, sort desc; returns the flagged records ranked."""
    if not records:
        return []
    weights = {
        "momentum": cfg.ranking.weight_momentum,
        "zone_confluence": cfg.ranking.weight_zone_confluence,
        "rsi_quality": cfg.ranking.weight_rsi_quality,
        "liquidity": cfg.ranking.weight_liquidity,
        "recency": cfg.ranking.weight_recency,
        "volume_expansion": cfg.ranking.weight_volume_expansion,
    }
    for r in records:
        r["metrics"] = compute_metrics(r)

    zcols = {}
    for m in METRICS:
        zcols[m] = _nan_z([r["metrics"][m] for r in records])

    for i, r in enumerate(records):
        score = 0.0
        r["z"] = {}
        for m in METRICS:
            z = float(zcols[m][i])
            r["z"][m] = z
            score += weights[m] * z
        r["score"] = score

    def sort_key(r):
        # desc score, then (small-cohort fallback) momentum, then liquidity,
        # then uncensored before censored.
        return (
            r["score"],
            r["metrics"]["momentum"],
            r["liquidity"],
            0 if r["rsi_check"] == "uncensored" else -1,
        )

    ranked = sorted(records, key=sort_key, reverse=True)

    if cfg.ranking.min_score is not None:
        ranked = [r for r in ranked if r["score"] >= cfg.ranking.min_score]

    for pos, r in enumerate(ranked, 1):
        r["rank"] = pos
    return ranked

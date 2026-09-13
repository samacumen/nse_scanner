"""Daily MACD-histogram bullish divergence (blueprint 8.2).

Prominence-based trough detection (scipy.find_peaks) is the pinned default;
'strict' (literal one-trough-per-negative-segment) is a fully-working option.
Guards: causality (>=K bars after recent), recency, min trough separation,
confirmation (rising run incl. trough->next, or zero-cross).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

# --- Fixed in code (blueprint 6 "Fixed in code") ---
TROUGH_MIN_DISTANCE = 3          # find_peaks min spacing (dedupe adjacent minima)
PROMINENCE_SCALE = "max"         # threshold = frac * max(|H|) over lookback (validated)


@dataclass
class Divergence:
    is_true: bool
    reason: str = ""
    prev: Optional[int] = None
    recent: Optional[int] = None
    h_prev: float = float("nan")
    h_recent: float = float("nan")
    pl_prev: float = float("nan")
    pl_recent: float = float("nan")
    swing_prev_date: Optional[pd.Timestamp] = None
    swing_low_date: Optional[pd.Timestamp] = None
    prev_date: Optional[pd.Timestamp] = None
    recent_date: Optional[pd.Timestamp] = None
    momentum_ok: bool = False
    price_ok: bool = False
    confirmed: bool = False


def neg_run_len(h: np.ndarray, i: int) -> int:
    """Length of the maximal H<0 run containing bar i (blueprint 8.2)."""
    if h[i] >= 0:
        return 0
    lo = i
    while lo - 1 >= 0 and h[lo - 1] < 0:
        lo -= 1
    hi = i
    while hi + 1 < len(h) and h[hi + 1] < 0:
        hi += 1
    return hi - lo + 1


def _troughs_prominence(h: np.ndarray, lookback: int, prom_frac: float, min_seg: int):
    n = len(h)
    w = h[max(0, n - lookback):]
    scale = float(np.nanmax(np.abs(w))) if len(w) else 0.0
    if not scale or np.isnan(scale):
        scale = 1.0
    min_prom = prom_frac * scale
    peaks, _ = find_peaks(-h, prominence=min_prom, distance=TROUGH_MIN_DISTANCE)
    return [int(p) for p in peaks if h[p] < 0 and neg_run_len(h, p) >= min_seg]


def _troughs_strict(h: np.ndarray, min_seg: int):
    """Literal spec: one trough (min-H bar) per maximal negative run/segment.

    Segments are separated by non-negative bars (zero crossings), so any two
    troughs from different segments have a positive/zero bar between them.
    """
    troughs = []
    n = len(h)
    i = 0
    while i < n:
        if h[i] < 0:
            j = i
            while j + 1 < n and h[j + 1] < 0:
                j += 1
            seg_len = j - i + 1
            if seg_len >= min_seg:
                seg = h[i:j + 1]
                troughs.append(i + int(np.argmin(seg)))
            i = j + 1
        else:
            i += 1
    return troughs


def find_troughs(H: pd.Series, cfg) -> list:
    """Return trough bar indices whose DATE falls in the last LOOKBACK sessions."""
    h = H.values
    n = len(h)
    dv = cfg.divergence
    if dv.trough_detection == "prominence":
        raw = _troughs_prominence(h, dv.lookback_days, dv.prominence_frac, dv.min_segment_len)
    else:  # strict
        raw = _troughs_strict(h, dv.min_segment_len)
    lb = dv.lookback_days
    return [t for t in raw if t >= n - lb]


def _price_low(df: pd.DataFrame, t: int, k: int, field: str):
    lo = max(0, t - k)
    hi = min(len(df) - 1, t + k)
    win = df[field].iloc[lo:hi + 1]
    return float(win.min()), win.idxmin()  # idxmin -> earliest bar on ties


def detect_divergence(df: pd.DataFrame, H: pd.Series, cfg) -> Divergence:
    dv = cfg.divergence
    k = dv.price_window_k
    field = dv.price_field
    n = len(df)
    h = H.values

    troughs = find_troughs(H, cfg)
    if len(troughs) < 2:
        return Divergence(False, reason="fewer_than_two_troughs")

    # recent = latest trough with >=K bars after it (causality) AND within recency window.
    recent = None
    for t in reversed(troughs):
        if t <= n - 1 - k and t >= n - 1 - dv.recency_bars:
            recent = t
            break
    if recent is None:
        return Divergence(False, reason="no_causal_recent_trough")

    # prev trough before recent (scope-dependent).
    priors = [t for t in troughs if t < recent]
    prev = None
    if dv.divergence_scope == "two_most_recent":
        for t in reversed(priors):
            if recent - t >= dv.min_trough_sep:
                prev = t
                break
    else:  # recent_vs_deepest_prior: deepest (min-H) trough before recent, honoring separation
        eligible = [t for t in priors if recent - t >= dv.min_trough_sep]
        if eligible:
            prev = min(eligible, key=lambda t: h[t])
    if prev is None:
        return Divergence(False, reason="no_prior_trough_with_separation")

    pl_prev, sd_prev = _price_low(df, prev, k, field)
    pl_recent, sd_recent = _price_low(df, recent, k, field)

    momentum_ok = bool(h[recent] > h[prev])
    price_ok = bool(pl_recent <= pl_prev * (1.0 + dv.tolerance_pct))

    # confirmation: rising run from recent (incl. recent->recent+1) >= confirm_bars,
    #   OR H crosses > 0 after recent. (blueprint 8.2)
    if dv.require_confirmation:
        after = h[recent + 1:]
        rising = 0
        prevv = h[recent]
        for v in after:
            if v > prevv:
                rising += 1
                prevv = v
            else:
                break
        confirmed = bool(rising >= dv.confirm_bars or (len(after) and (after > 0).any()))
    else:
        confirmed = True

    is_true = momentum_ok and price_ok and confirmed
    return Divergence(
        is_true=is_true,
        reason="divergence" if is_true else "criteria_not_met",
        prev=prev,
        recent=recent,
        h_prev=float(h[prev]),
        h_recent=float(h[recent]),
        pl_prev=pl_prev,
        pl_recent=pl_recent,
        swing_prev_date=pd.Timestamp(sd_prev),
        swing_low_date=pd.Timestamp(sd_recent),
        prev_date=pd.Timestamp(df.index[prev]),
        recent_date=pd.Timestamp(df.index[recent]),
        momentum_ok=momentum_ok,
        price_ok=price_ok,
        confirmed=confirmed,
    )

"""Daily MACD-histogram bullish divergence (NSE Scanner Rule Spec v1.2, sec 1.3-2).

Trough (spec 1.3) = a local pivot of the histogram in negative territory: a bar t
with H(t) < 0 whose H is <= every other H in the window [t - TROUGH_PIVOT_K,
t + TROUGH_PIVOT_K]; on an adjacent tie the earliest bar is the trough. This finds
overlapping troughs (several within one negative excursion), not just one per
zero-crossed segment. The two MOST RECENT troughs in the last LOOKBACK_DAYS are
compared (spec 2): momentum higher-low AND price lower/equal-low.

Guards kept from the build (never loosen the spec, only avoid bad picks):
- causality - a pivot is only knowable once TROUGH_PIVOT_K closed bars follow it
  (no look-ahead), and the swing-low window must be fully in range;
- recency - the recent trough must be within RECENCY_BARS of the last bar;
- confirmation - the recent dip must have turned back up (avoids falling knives).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


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


def pivot_troughs(h: np.ndarray, k: int) -> list:
    """Spec 1.3 troughs: bar indices t with h[t] < 0 and h[t] <= h[j] for every
    j in [t-k, t+k] (j != t). A full +-k window is required (no look-ahead - a
    pivot is only confirmable once k closed bars follow it). Adjacent bars that tie
    for the minimum collapse to the earliest.
    """
    n = len(h)
    out: list = []
    prev_idx = -2
    prev_val = 0.0
    for t in range(k, n - k):
        if not h[t] < 0:
            continue
        is_trough = True
        for j in range(t - k, t + k + 1):
            if j == t:
                continue
            if h[j] < h[t]:
                is_trough = False
                break
        if not is_trough:
            continue
        if t == prev_idx + 1 and h[t] == prev_val:
            prev_idx = t  # extend an adjacent tie-run; the earliest is already kept
            continue
        out.append(t)
        prev_idx = t
        prev_val = h[t]
    return out


def find_troughs(H: pd.Series, cfg) -> list:
    """Return trough bar indices (spec 1.3) whose DATE falls in the last LOOKBACK sessions."""
    h = H.values
    n = len(h)
    dv = cfg.divergence
    raw = pivot_troughs(h, dv.trough_pivot_k)
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

    # recent = latest trough whose swing-low window is fully known (causality) AND
    # within the recency window.
    recent = None
    for t in reversed(troughs):
        if t <= n - 1 - k and t >= n - 1 - dv.recency_bars:
            recent = t
            break
    if recent is None:
        return Divergence(False, reason="no_causal_recent_trough")

    # prev = the trough immediately before recent (spec 2: the two most recent troughs).
    priors = [t for t in troughs if t < recent]
    if not priors:
        return Divergence(False, reason="no_prior_trough")
    prev = priors[-1]

    pl_prev, sd_prev = _price_low(df, prev, k, field)
    pl_recent, sd_recent = _price_low(df, recent, k, field)

    momentum_ok = bool(h[recent] > h[prev])
    price_ok = bool(pl_recent <= pl_prev * (1.0 + dv.tolerance_pct))

    # confirmation: rising run from recent (incl. recent->recent+1) >= confirm_bars,
    #   OR H crosses > 0 after recent.
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

"""Daily MACD-histogram bullish divergence (NSE Scanner Rule Spec v1.3, sec 1.3-2).

Trough (spec 1.3) = a local pivot of the histogram in negative territory: a bar t
with H(t) < 0 whose H is <= every other H in the window [t - TROUGH_PIVOT_K,
t + TROUGH_PIVOT_K] (v1.3: K = 1, the day before and the day after); on an adjacent
tie the earliest bar is the trough. Only the two MOST RECENT troughs in the last
LOOKBACK_DAYS are tested (spec 2); if they fail, the stock is not flagged (never an
older or alternative pair). Divergence = all of:
  - momentum: H(recent) > H(prev)                                     (spec 2)
  - price: PriceLow(recent) <= PriceLow(prev) * (1 + TOLERANCE_PCT)    (spec 2)
  - no intervening breach: no bar strictly between the two trough dates trades
    below the lower of the two price lows                              (spec 2 v1.3; user: "lowest dip")
  - two separate price dips: the two price lows are different days, the earlier
    low before the recent trough and the recent low after the earlier trough  (user decision)
  - momentum at the low: H on the recent price-low day > H(prev)       (user decision)
Freshness only feeds ranking.

Closed bars only (spec 7.5): a pivot is only knowable once TROUGH_PIVOT_K closed bars
follow it. The +-PRICE_WINDOW_K price/RSI window of a trough younger than that many
sessions is cut at the latest close (user decision: judge now) and flagged as open.
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
    between_low: float = float("nan")              # lowest price strictly between the two trough dates
    between_low_date: Optional[pd.Timestamp] = None
    no_breach_ok: bool = False
    separate_lows_ok: bool = False
    h_at_low: float = float("nan")                 # H on the recent price-low day
    momentum_at_low_ok: bool = False
    window_open: bool = False                      # recent window cut at the latest close


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

    # spec 2: only the two most recent troughs are ever tested.
    prev, recent = troughs[-2], troughs[-1]
    pl_prev, sd_prev = _price_low(df, prev, k, field)
    pl_recent, sd_recent = _price_low(df, recent, k, field)
    prev_date, recent_date = df.index[prev], df.index[recent]

    momentum_ok = bool(h[recent] > h[prev])
    price_ok = bool(pl_recent <= pl_prev * (1.0 + dv.tolerance_pct))
    # spec 2 (v1.3): nothing strictly between the two trough dates below the lower of the two lows
    between = df[field].iloc[prev + 1:recent]
    between_low = float(between.min()) if len(between) else float("nan")
    no_breach_ok = bool(len(between) == 0 or between_low >= min(pl_prev, pl_recent))
    # two separate price dips, each low on its own side of the other trough
    separate_lows_ok = bool(sd_prev < sd_recent and sd_prev < recent_date and sd_recent > prev_date)
    h_at_low = float(h[df.index.get_loc(sd_recent)])
    momentum_at_low_ok = bool(h_at_low > h[prev])

    if not (momentum_ok and price_ok):
        reason = "criteria_not_met"
    elif not no_breach_ok:
        reason = "intervening_breach"
    elif not separate_lows_ok:
        reason = "same_price_dip"
    elif not momentum_at_low_ok:
        reason = "momentum_lower_at_low"
    else:
        reason = "divergence"
    return Divergence(
        is_true=reason == "divergence",
        reason=reason,
        prev=prev,
        recent=recent,
        h_prev=float(h[prev]),
        h_recent=float(h[recent]),
        pl_prev=pl_prev,
        pl_recent=pl_recent,
        swing_prev_date=pd.Timestamp(sd_prev),
        swing_low_date=pd.Timestamp(sd_recent),
        prev_date=pd.Timestamp(prev_date),
        recent_date=pd.Timestamp(recent_date),
        momentum_ok=momentum_ok,
        price_ok=price_ok,
        between_low=between_low,
        between_low_date=pd.Timestamp(between.idxmin()) if len(between) else None,
        no_breach_ok=no_breach_ok,
        separate_lows_ok=separate_lows_ok,
        h_at_low=h_at_low,
        momentum_at_low_ok=momentum_at_low_ok,
        window_open=recent + k > n - 1,
    )

"""Weekly EMA(11/22/50) support zone (blueprint 8.3).

Only evaluated when divergence is true. Requires >= min_weekly_bars_for_zone
weekly bars (B1 gate). Closed-week rule: only the most-recent bucket can be
'forming'; a swing low there defers (pending_week).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .indicators import ema, weekly

# Fixed in code (blueprint 6): resample rule = W-FRI (NSE week); anchor = swing-low week.
RESAMPLE_RULE = "W-FRI"


@dataclass
class Zone:
    status: str                    # ok | pending_week | no_week | insufficient_weekly
    zone_ok: bool = False
    W: Optional[pd.Timestamp] = None
    emas: dict = field(default_factory=dict)
    band_lo: float = float("nan")
    band_hi: float = float("nan")
    band_mid: float = float("nan")
    week_low: float = float("nan")
    week_high: float = float("nan")
    week_close: float = float("nan")


def _closed(W: pd.Timestamp, buckets, last_date: pd.Timestamp) -> bool:
    """W is closed iff a later bucket has data OR scan/as-of date >= W's Friday label."""
    if W != buckets[-1]:
        return True
    return pd.Timestamp(last_date) >= W


def weekly_zone(daily: pd.DataFrame, swing_low_date, cfg) -> Zone:
    wk = weekly(daily, RESAMPLE_RULE)
    if len(wk) < cfg.weekly.min_weekly_bars_for_zone:
        return Zone(status="insufficient_weekly")

    buckets = list(wk.index)
    last_date = daily.index.max()
    emas = {p: ema(wk["Close"], p) for p in cfg.weekly.ema_set}

    swing = pd.Timestamp(swing_low_date)
    cand = [b for b in buckets if b >= swing]
    if not cand:
        return Zone(status="no_week")
    W = cand[0]  # W-FRI bucket containing the swing-low date
    if not _closed(W, buckets, last_date):
        return Zone(status="pending_week", W=W)

    vals = {p: float(emas[p].loc[W]) for p in cfg.weekly.ema_set}
    lo = min(vals.values())
    hi = max(vals.values())
    row = wk.loc[W]
    wlow, whigh, wclose = float(row["Low"]), float(row["High"]), float(row["Close"])

    if cfg.weekly.zone_test == "range_overlap":
        zone_ok = bool(wlow <= hi and whigh >= lo)
    else:  # close_in_band (stricter): the weekly close must sit inside the band
        zone_ok = bool(lo <= wclose <= hi)

    return Zone(
        status="ok",
        zone_ok=zone_ok,
        W=W,
        emas=vals,
        band_lo=lo,
        band_hi=hi,
        band_mid=(lo + hi) / 2.0,
        week_low=wlow,
        week_high=whigh,
        week_close=wclose,
    )

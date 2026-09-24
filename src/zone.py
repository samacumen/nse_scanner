"""Weekly EMA(11/22/50) support zone (blueprint 8.3).

Only evaluated when divergence is true. Requires >= min_weekly_bars_for_zone
weekly bars. Closed-week rule (spec 7.5): only the most-recent bucket can be
'forming'; it counts as closed once the data was downloaded after that week's
Friday 15:30 IST close (so a Friday exchange holiday needs no calendar). A swing
low in a still-forming week defers (pending_week).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .indicators import ema, weekly
from .store import session_close_utc

# Fixed in code (blueprint 6): resample rule = W-FRI (NSE week); anchor = swing-low week.
RESAMPLE_RULE = "W-FRI"


@dataclass
class Zone:
    status: str                    # ok | pending_week | no_week | insufficient_weekly
    zone_ok: bool = False
    W: Optional[pd.Timestamp] = None          # W-FRI bucket label (the week's Friday)
    week_start: Optional[pd.Timestamp] = None  # first trading day in bucket W (spec 3.1 Zone_week_date)
    emas: dict = field(default_factory=dict)
    band_lo: float = float("nan")
    band_hi: float = float("nan")
    band_mid: float = float("nan")
    week_low: float = float("nan")
    week_high: float = float("nan")
    week_close: float = float("nan")


def _closed(W: pd.Timestamp, buckets, last_date: pd.Timestamp, fetched_at=None) -> bool:
    """W (labelled by its Friday) is closed iff a later week has data, OR the data was
    downloaded at/after W's Friday 15:30 IST close. With no recorded download time,
    fall back to 'W's Friday bar is in the data'."""
    if W != buckets[-1]:
        return True
    if fetched_at is None:
        return pd.Timestamp(last_date) >= W
    return fetched_at >= session_close_utc(W)


def weekly_zone(daily: pd.DataFrame, swing_low_date, cfg, fetched_at=None) -> Zone:
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
    # Zone_week_date (spec 3.1) = the START date of candle W = its first trading day.
    week_start = pd.Timestamp(daily.index.to_series().resample(RESAMPLE_RULE).min().loc[W])
    if not _closed(W, buckets, last_date, fetched_at):
        return Zone(status="pending_week", W=W, week_start=week_start)

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
        week_start=week_start,
        emas=vals,
        band_lo=lo,
        band_hi=hi,
        band_mid=(lo + hi) / 2.0,
        week_low=wlow,
        week_high=whigh,
        week_close=wclose,
    )

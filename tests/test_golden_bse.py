"""BSE GOLDEN test (blueprint 4a / 11) - the spec's own diagram, under Rule Spec v1.3.

Runs the src pipeline on a FROZEN copy of BSE's stored data (6y, last bar
2026-09-22, tests/fixtures/) cut at two dates and asserts the diagram-exact numbers:
  Trough_prev 2026-08-21 (H -18.15), Trough_recent 2026-09-02 (H -3.49, low 3131.5),
  lowest low in between 3216.30 on 2026-08-31, weekly W ending 2026-09-04 band
  [3178.3, 3520.1], zone_ok, RSI_trough 33.34 uncensored.
  - 2026-09-04: the diagram's own bar (O 3400 H 3474 L 3391.7). The 09-02 dip is two sessions
    old, so its +-3 window is cut at the latest close (judged now, marked open).
  - 2026-09-18: the window is complete; same numbers.
With the 1-day trough rule BSE's 2026-09-21 dip is a trough once 09-22 closes, so the full
fixture compares 09-02 -> 09-21 instead; hence the cuts.
(Yahoo's 6 holiday/placeholder filler rows in this file are dropped on load; before that
rule the values were H -18.127 / -3.491 and RSI 33.29 - same dates, lows, band and zone.)

Offline and deterministic: live data keeps moving, so a live fetch cannot pin these numbers.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src import store as storemod
from src import indicators as ind
from src.divergence import detect_divergence
from src.zone import weekly_zone


FIXTURE = ROOT / "tests" / "fixtures" / "BSE_2026-09-22.parquet"


@pytest.fixture(scope="module", params=["2026-09-04", "2026-09-18"])
def bse_pipeline(request):
    cfg = load_config()
    full, _meta = storemod.load_parquet(FIXTURE)
    assert full.index.max().date().isoformat() == "2026-09-22"
    df = full.loc[:request.param]
    H = ind.macd_hist(df["Close"], cfg.macd.fast, cfg.macd.slow, cfg.macd.signal)
    rsi = ind.rsi(df["Close"], cfg.rsi.period, cfg.rsi.smoothing)
    div = detect_divergence(df, H, cfg)
    zone = weekly_zone(df, div.swing_low_date, cfg)
    return cfg, df, H, rsi, div, zone


def test_troughs(bse_pipeline):
    cfg, df, H, rsi, div, zone = bse_pipeline
    assert div.is_true
    assert div.prev_date.date().isoformat() == "2026-08-21"
    assert div.recent_date.date().isoformat() == "2026-09-02"
    assert abs(div.h_prev - (-18.153)) < 0.005
    assert abs(div.h_recent - (-3.493)) < 0.005
    assert abs(div.pl_prev - 3223.00) < 0.5
    assert abs(div.pl_recent - 3131.50) < 0.5
    assert abs(div.between_low - 3216.30) < 0.005 and div.between_low_date.date().isoformat() == "2026-08-31"
    assert div.window_open == (df.index[-1].date().isoformat() == "2026-09-04")


def test_weekly_zone(bse_pipeline):
    cfg, df, H, rsi, div, zone = bse_pipeline
    assert zone.status == "ok"
    assert zone.W.date().isoformat() == "2026-09-04"          # W-FRI bucket label (Friday)
    assert zone.week_start.date().isoformat() == "2026-08-31"  # Zone_week_date = week start (Mon)
    assert abs(zone.band_lo - 3178.3) < 1.0
    assert abs(zone.band_hi - 3520.1) < 1.0
    assert zone.zone_ok is True


def test_rsi_trough(bse_pipeline):
    cfg, df, H, rsi, div, zone = bse_pipeline
    k = cfg.divergence.price_window_k
    lo = max(0, div.recent - k)
    hi = min(len(rsi) - 1, div.recent + k)
    rtv = float(rsi.iloc[lo:hi + 1].min())
    assert abs(rtv - 33.34) < 0.01
    assert rtv >= cfg.rsi.lower_band  # uncensored

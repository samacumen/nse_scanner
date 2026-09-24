"""BSE GOLDEN test (blueprint 4a / 11).

Runs the src pipeline on a FROZEN copy of BSE's stored data (6y, last bar
2026-09-22, tests/fixtures/) and asserts the diagram-exact numbers:
  Trough_prev 2026-08-21 (H -18.13), Trough_recent 2026-09-02 (low 3131.5),
  weekly W ending 2026-09-04 band [3178.3, 3520.1], zone_ok,
  RSI_trough 33.29 uncensored.

Offline and deterministic: live data keeps moving (BSE formed a new, lower
momentum trough on 2026-09-21), so a live fetch cannot pin these numbers.
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


@pytest.fixture(scope="module")
def bse_pipeline():
    cfg = load_config()
    df, _meta = storemod.load_parquet(FIXTURE)
    assert df.index.max().date().isoformat() == "2026-09-22"
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
    assert abs(div.h_prev - (-18.127)) < 0.05
    assert abs(div.h_recent - (-3.491)) < 0.05
    assert abs(div.pl_prev - 3223.00) < 0.5
    assert abs(div.pl_recent - 3131.50) < 0.5


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
    assert abs(rtv - 33.29) < 0.1
    assert rtv >= cfg.rsi.lower_band  # uncensored

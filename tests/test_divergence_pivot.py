"""Unit golden for the v1.2 pivot trough rule (spec 1.3 / 2).

Offline (no network): proves the exact behaviour the v1.2 change hinges on -
  1) OVERLAPPING troughs: two local minima inside ONE negative excursion are both
     found (the old one-trough-per-zero-crossed-segment rule would find only one);
  2) adjacent ties collapse to the EARLIEST bar;
  3) end-of-series pivots are not reported until a full +-K window exists (no look-ahead);
  4) a full bullish divergence (momentum higher-low + price lower-low + confirmation)
     is detected end to end.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.divergence import pivot_troughs, detect_divergence


def test_overlapping_troughs_in_one_negative_run():
    # One contiguous H<0 run (idx 0..11) with TWO distinct local minima at idx 3 and 9.
    h = np.array([-0.5, -1.0, -2.0, -5.0, -2.0, -1.5, -1.0,
                  -2.0, -4.0, -6.0, -3.0, -1.0, 0.5, 1.0, 1.5])
    troughs = pivot_troughs(h, 3)
    assert troughs == [3, 9]
    # both are in the SAME negative excursion (no zero-cross between them) -> "overlapping"
    assert all(h[i] < 0 for i in range(3, 10))


def test_adjacent_tie_takes_earliest():
    h = np.array([-1.0, -3.0, -5.0, -5.0, -3.0, -1.0, -0.5, 0.5])
    assert pivot_troughs(h, 2) == [2]  # idx 3 ties with idx 2 -> earliest kept


def test_no_lookahead_at_series_end():
    # A minimum in the last K bars cannot be confirmed (needs K closed bars after it).
    h = np.array([-1.0, -2.0, -1.0, -0.5, -2.0, -5.0])  # deepest is the LAST bar
    assert pivot_troughs(h, 3) == []


def test_end_to_end_bullish_divergence():
    n = 15
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    h = np.array([-0.5, -1.0, -3.0, -6.0, -3.0, -1.5, -1.0,
                  -1.5, -2.5, -3.0, -1.5, -0.5, 0.5, 1.0, 1.5])
    low = np.array([110, 108, 105, 100, 103, 106, 107,
                    104, 101, 99, 102, 105, 108, 110, 112], dtype=float)
    df = pd.DataFrame({"Low": low}, index=idx)
    H = pd.Series(h, index=idx)
    cfg = load_config()
    div = detect_divergence(df, H, cfg)
    assert div.is_true
    assert div.prev_date.date().isoformat() == idx[3].date().isoformat()
    assert div.recent_date.date().isoformat() == idx[9].date().isoformat()
    assert div.h_recent > div.h_prev            # momentum higher-low
    assert div.pl_recent <= div.pl_prev         # price lower/equal-low
    assert div.momentum_ok and div.price_ok and div.confirmed

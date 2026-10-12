"""Unit golden for the pivot trough rule and the pair conditions (spec 1.3 / 2, Rule Spec v1.3).

Offline (no network): proves the exact behaviour the rules hinge on -
  1) OVERLAPPING troughs: two local minima inside ONE negative excursion are both
     found (the old one-trough-per-zero-crossed-segment rule would find only one);
  2) adjacent ties collapse to the EARLIEST bar;
  3) end-of-series pivots are not reported until a full +-K window exists (no look-ahead);
  4) a full bullish divergence (momentum higher-low + price lower-low) is detected
     end to end;
  5) the pair compared is ALWAYS the two most recent troughs; a newest trough younger than
     its +-PRICE_WINDOW_K window is judged now on the closed bars (marked open), never an
     older pair instead;
  6) v1.3 no intervening breach: a bar between the two troughs below the lower of the two
     lows fails the pair (NH); the earlier dip's own low never does (CENTRALBK);
  7) two momentum wiggles in ONE price dip (same or crossed lows, ABSLAMC / KIMS) and a recent
     low where momentum sits below the earlier trough (CHOLAFIN) are not divergences.
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
    assert div.momentum_ok and div.price_ok


def _three_trough_series(n):
    """Positive H except V-shaped dips with minima at 45 (-9), 65 (-6), 76 (-3); price falls."""
    h = np.full(n, 0.5)
    for t, v in [(45, -9.0), (65, -6.0), (76, -3.0)]:
        h[t - 2], h[t - 1], h[t], h[t + 1], h[t + 2] = v / 3, v / 2, v, v / 2, v / 3
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    low = np.linspace(200, 100, n)
    return pd.DataFrame({"Low": low}, index=idx), pd.Series(h, index=idx)


def test_pair_is_two_most_recent_troughs():
    df, H = _three_trough_series(80)
    cfg = load_config()  # pivot K = 1, price K = 3
    div = detect_divergence(df, H, cfg)
    assert (div.prev, div.recent) == (65, 76) and div.is_true and not div.window_open


def test_a_fresh_trough_is_judged_now_never_an_older_pair():
    df, H = _three_trough_series(80)
    cfg = load_config()
    cfg.divergence.price_window_k = 5  # trough 76 is a pivot, but [71, 81] is not closed yet
    div = detect_divergence(df, H, cfg)
    assert (div.prev, div.recent) == (65, 76) and div.is_true and div.window_open
    assert div.swing_low_date == df.index[79]  # the window is cut at the latest close
    df2, H2 = _three_trough_series(82)  # two more closed bars -> the window closes
    div2 = detect_divergence(df2, H2, cfg)
    assert (div2.prev, div2.recent) == (65, 76) and not div2.window_open


def _pair(h_points, low_points, n=20):
    """H = +0.5 and Low = 110 except at the given {bar: value} points."""
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    h = np.full(n, 0.5)
    low = np.full(n, 110.0)
    for i, v in h_points.items():
        h[i] = v
    for i, v in low_points.items():
        low[i] = v
    return pd.DataFrame({"Low": low}, index=idx), pd.Series(h, index=idx)


V4_V14 = {3: -3.0, 4: -6.0, 5: -3.0, 13: -1.5, 14: -3.0, 15: -1.5}  # troughs at 4 and 14, higher low


def test_a_lower_dip_between_the_troughs_fails_the_pair():
    cfg = load_config()
    df, H = _pair(V4_V14, {4: 100.0, 14: 98.0})
    assert detect_divergence(df, H, cfg).is_true
    df, H = _pair(V4_V14, {4: 100.0, 9: 95.0, 14: 98.0})  # an orphan dip below both lows (NH)
    div = detect_divergence(df, H, cfg)
    assert div.momentum_ok and div.price_ok and not div.no_breach_ok
    assert not div.is_true and div.reason == "intervening_breach"
    assert div.between_low == 95.0 and div.between_low_date == df.index[9]


def test_equal_low_floor_is_the_lower_of_the_two_lows():
    cfg = load_config()
    # the earlier dip's own low (100 on bar 5) prints a day after its trough, inside the
    # between-dates; the recent low 100.5 is an equal low within the 1% tolerance (CENTRALBK)
    df, H = _pair(V4_V14, {5: 100.0, 14: 100.5})
    div = detect_divergence(df, H, cfg)
    assert div.between_low == 100.0 and div.no_breach_ok and div.is_true
    df, H = _pair(V4_V14, {5: 100.0, 9: 99.9, 14: 100.5})  # but a bar below the lower low fails
    assert detect_divergence(df, H, cfg).reason == "intervening_breach"


def test_two_wiggles_in_one_price_dip_are_not_a_divergence():
    cfg = load_config()
    wiggle = {9: -2.0, 10: -5.0, 11: -3.0, 12: -4.0, 13: -1.0}  # troughs 10 and 12 (higher low)
    df, H = _pair(wiggle, {10: 100.0})  # both windows find the same low day (ABSLAMC)
    div = detect_divergence(df, H, cfg)
    assert (div.prev, div.recent) == (10, 12) and div.momentum_ok and div.price_ok and div.no_breach_ok
    assert div.swing_prev_date == div.swing_low_date and div.reason == "same_price_dip"
    crossed = {9: -2.0, 10: -5.0, 11: -3.0, 12: -3.5, 13: -4.0, 14: -1.0}  # troughs 10 and 13
    df, H = _pair(crossed, {13: 100.2, 15: 100.0})  # the earlier low sits ON the recent trough (KIMS)
    div = detect_divergence(df, H, cfg)
    assert (div.prev, div.recent) == (10, 13) and div.swing_prev_date == df.index[13]
    assert div.momentum_ok and div.price_ok and div.reason == "same_price_dip"
    df, H = _pair(crossed, {8: 100.0, 10: 100.5})  # the recent low sits ON the earlier trough (AMBIKCO, VETO)
    div = detect_divergence(df, H, cfg)
    assert div.swing_prev_date == df.index[8] and div.swing_low_date == df.index[10] == div.prev_date
    assert div.momentum_ok and div.price_ok and div.no_breach_ok
    assert not div.separate_lows_ok and div.reason == "same_price_dip"


def test_momentum_lower_at_the_recent_low_is_not_a_divergence():
    cfg = load_config()
    # trough 14 is a wiggle; price bottoms two days later while H is below the earlier trough (CHOLAFIN)
    falling = {3: -3.0, 4: -6.0, 5: -3.0, 13: -2.5, 14: -3.0, 15: -2.0, 16: -7.0, 17: -8.0}
    df, H = _pair(falling, {4: 100.0, 16: 95.0}, n=18)
    div = detect_divergence(df, H, cfg)
    assert (div.prev, div.recent) == (4, 14) and div.momentum_ok and div.price_ok
    assert div.swing_low_date == df.index[16] and div.h_at_low == -7.0
    assert not div.momentum_at_low_ok and div.reason == "momentum_lower_at_low"

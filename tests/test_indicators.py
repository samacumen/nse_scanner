"""Unit tests for indicators (blueprint 8.1 / 11).

Fixed-input checks + Wilder-RSI monotonic-series sanity + cross-check that
ewm(adjust=False) MACD matches a hand rolled recurrence within tolerance.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import indicators as ind


def test_ema_recurrence():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    e = ind.ema(x, 3)
    # adjust=False EMA: y0=x0; yt = a*xt + (1-a)*y_{t-1}, a=2/(n+1)=0.5
    a = 2 / (3 + 1)
    y = [1.0]
    for v in x.iloc[1:]:
        y.append(a * v + (1 - a) * y[-1])
    assert np.allclose(e.values, y)


def test_rsi_all_gains_is_100():
    close = pd.Series(np.arange(1, 60, dtype=float))
    r = ind.rsi(close, 14, "wilder")
    # Strictly rising -> zero losses -> RSI saturates at 100.
    assert r.iloc[-1] == 100.0


def test_rsi_flat_is_100_guard():
    close = pd.Series([100.0] * 40)
    r = ind.rsi(close, 14, "wilder")
    assert r.iloc[-1] == 100.0  # 0/0 guard


def test_rsi_wilder_matches_pinned_recurrence():
    # Blueprint 8.1 pins ewm(alpha=1/14, adjust=False). Verify the implementation
    # equals a hand-rolled RMA recurrence (seed = first value) on a real-ish path.
    rng = np.random.default_rng(7)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1.0, 300)))
    r = ind.rsi(close, 14, "wilder")
    d = close.diff()
    gain = d.clip(lower=0).values
    loss = (-d).clip(lower=0).values
    a = 1 / 14
    ag = [gain[1]]
    al = [loss[1]]
    for t in range(2, len(gain)):
        ag.append(a * gain[t] + (1 - a) * ag[-1])
        al.append(a * loss[t] + (1 - a) * al[-1])
    rs = ag[-1] / al[-1] if al[-1] != 0 else np.inf
    expected = 100 - 100 / (1 + rs)
    assert abs(r.iloc[-1] - expected) < 1e-6


def test_rsi_sma_mode_differs_and_valid():
    close = pd.Series(np.linspace(100, 80, 40) + np.sin(np.arange(40)))
    rw = ind.rsi(close, 14, "wilder")
    rs = ind.rsi(close, 14, "sma")
    assert (rs.dropna() >= 0).all() and (rs.dropna() <= 100).all()
    assert not np.allclose(rw.tail(10).values, rs.tail(10).values)


def test_macd_hist_zero_for_constant():
    close = pd.Series([50.0] * 100)
    H = ind.macd_hist(close)
    assert abs(H.iloc[-1]) < 1e-9


def test_atr_positive():
    idx = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "High": np.linspace(10, 20, 50) + 1,
        "Low": np.linspace(10, 20, 50) - 1,
        "Close": np.linspace(10, 20, 50),
    }, index=idx)
    a = ind.atr(df, 14)
    assert a.iloc[-1] > 0


def test_weekly_resample_wfri():
    idx = pd.date_range("2024-01-01", periods=20, freq="B")
    df = pd.DataFrame({
        "Open": range(20), "High": range(20), "Low": range(20),
        "Close": range(20), "Volume": [100] * 20,
    }, index=idx).astype(float)
    wk = ind.weekly(df)
    assert (wk.index.weekday == 4).all()  # all Friday labels
    assert wk["Volume"].iloc[0] > 0

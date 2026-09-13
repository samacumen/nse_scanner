"""Indicators - exactly per blueprint 8.1.

All computed on the FULL warmed series (never a truncated slice).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(x: pd.Series, n: int) -> pd.Series:
    """Exponential MA with adjust=False (blueprint 8.1)."""
    return x.ewm(span=n, adjust=False).mean()


def macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """MACD histogram H = macd_line - signal (12/26/9, ewm adjust=False)."""
    macd_line = ema(close, fast) - ema(close, slow)
    sig = ema(macd_line, signal)
    return macd_line - sig


def rsi(close: pd.Series, period: int = 14, smoothing: str = "wilder") -> pd.Series:
    """RSI(period). smoothing: 'wilder' (RMA) | 'sma' (simple MA of gains/losses).

    0/0 flat -> 100 (blueprint 8.1 guard).
    """
    d = close.diff()
    gain = d.clip(lower=0)
    loss = (-d).clip(lower=0)
    if smoothing == "wilder":
        ag = gain.ewm(alpha=1.0 / period, adjust=False).mean()
        al = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    elif smoothing == "sma":
        ag = gain.rolling(window=period, min_periods=period).mean()
        al = loss.rolling(window=period, min_periods=period).mean()
    else:
        raise ValueError(f"unknown rsi smoothing {smoothing!r}")
    rs = ag / al.replace(0, np.nan)
    r = 100.0 - 100.0 / (1.0 + rs)
    return r.fillna(100.0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR(14) via Wilder RMA of true range (blueprint 8.1)."""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def weekly(daily: pd.DataFrame, rule: str = "W-FRI") -> pd.DataFrame:
    """Resample adjusted daily OHLCV to weekly W-FRI buckets (blueprint 8.1)."""
    wk = daily.resample(rule).agg(
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
    ).dropna(subset=["Close"])
    return wk

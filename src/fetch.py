"""Data fetch (blueprint 7 step 1/3).

yfinance primary (auto_adjust=False -> split-adjusted OHLC; keep Adj Close for
total_return), direct Yahoo chart-API fallback (browser UA). Startup smoke-fetch.
One bad symbol never aborts (caller catches).
"""
from __future__ import annotations

import json
import time
import urllib.request

import numpy as np
import pandas as pd

# Fixed in code (blueprint 6): fetch resilience knobs.
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 1.5
SMOKE_SYMBOL = "RELIANCE"

_UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json",
}
STD_COLS = ["Open", "High", "Low", "Close", "Volume", "AdjClose", "Dividends", "StockSplits"]


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex, normalize column names, ensure the audit columns exist."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    rename = {
        "Adj Close": "AdjClose", "Adj_Close": "AdjClose", "Adjclose": "AdjClose",
        "Stock Splits": "StockSplits", "Stock_Splits": "StockSplits",
    }
    df = df.rename(columns=rename)
    if "AdjClose" not in df.columns:
        df["AdjClose"] = df["Close"]
    if "Dividends" not in df.columns:
        df["Dividends"] = 0.0
    if "StockSplits" not in df.columns:
        df["StockSplits"] = 0.0
    df = df[[c for c in STD_COLS if c in df.columns]].copy()
    df = df.dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "date"
    return df


def fetch_yfinance(symbol: str, years: int) -> pd.DataFrame | None:
    import yfinance as yf
    df = yf.download(f"{symbol}.NS", period=f"{years}y", interval="1d",
                     auto_adjust=False, actions=True, progress=False, threads=False)
    if df is None or len(df) == 0:
        return None
    return _standardize(df)


def fetch_chart_api(symbol: str, years: int) -> pd.DataFrame:
    """Direct Yahoo chart API fallback (browser UA)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
           f"?range={years}y&interval=1d&events=splits")
    req = urllib.request.Request(url, headers=_UA)
    d = json.load(urllib.request.urlopen(req, timeout=25))
    res = d["chart"]["result"][0]
    idx = (pd.to_datetime(res["timestamp"], unit="s", utc=True)
           .tz_convert("Asia/Kolkata").normalize().tz_localize(None))
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "Open": q["open"], "High": q["high"], "Low": q["low"],
        "Close": q["close"], "Volume": q["volume"],
    }, index=idx)
    return _standardize(df)


def fetch_symbol(symbol: str, years: int) -> tuple[pd.DataFrame | None, str]:
    """Return (df, source). Retries yfinance with backoff, then chart-API fallback.

    Raises only if BOTH sources fail (caller logs as 'failed', continues).
    """
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            df = fetch_yfinance(symbol, years)
            if df is not None and len(df) > 0:
                return df, "yfinance"
        except Exception as e:  # noqa: BLE001
            last_exc = e
        time.sleep(BACKOFF_BASE_SEC * (attempt + 1))
    # Fallback
    df = fetch_chart_api(symbol, years)
    if df is not None and len(df) > 0:
        return df, "chart-api"
    raise RuntimeError(f"both sources returned no data for {symbol} ({last_exc})")


def smoke_fetch(years: int = 6) -> None:
    """Fail loudly if Yahoo's shape changed (blueprint 7 step 1)."""
    df, src = fetch_symbol(SMOKE_SYMBOL, years)
    need = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or len(df) < 200 or not need.issubset(set(df.columns)):
        raise RuntimeError(
            f"SMOKE-FETCH FAILED for {SMOKE_SYMBOL}: unexpected shape "
            f"(source={src}, rows={0 if df is None else len(df)}, "
            f"cols={None if df is None else list(df.columns)}). Aborting - Yahoo/yfinance drift."
        )
    if not np.isfinite(df["Close"].iloc[-1]):
        raise RuntimeError("SMOKE-FETCH FAILED: non-finite last close.")

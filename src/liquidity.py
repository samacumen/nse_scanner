"""Liquidity (blueprint 8.5).

liquidity = median(Close*Volume over last `window` days). Excluded from
flagging/ranking when apply_as_filter and (liquidity < floor OR last Close < min_price).
liquidity also feeds ranking.
"""
from __future__ import annotations

import pandas as pd


def median_traded_value(df: pd.DataFrame, window: int) -> float:
    return float((df["Close"] * df["Volume"]).tail(window).median())


def passes_liquidity(df: pd.DataFrame, cfg):
    """Return (ok: bool, liquidity: float, last_close: float)."""
    liq = median_traded_value(df, cfg.liquidity.window)
    last_close = float(df["Close"].iloc[-1])
    if not cfg.liquidity.apply_as_filter:
        return True, liq, last_close
    ok = liq >= cfg.liquidity.min_median_traded_value_inr and last_close >= cfg.liquidity.min_price
    return bool(ok), liq, last_close

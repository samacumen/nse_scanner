"""Storage + validation (blueprint 7 step 4/5, Appendix A).

Parquet per symbol with audit columns and file-level metadata
(symbol, isin, adjustment). Also manifest read/write.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .indicators import weekly

MANIFEST_COLUMNS = [
    "symbol", "isin", "ticker", "source", "rows",
    "first_date", "last_date", "status", "fetched_at",
]

OHLC = ["Open", "High", "Low", "Close"]
AUDIT = ["AdjClose", "Dividends", "StockSplits"]


def apply_adjustment(df: pd.DataFrame, price_adjustment: str) -> pd.DataFrame:
    """split_only -> keep raw (already split-adjusted by Yahoo).
    total_return -> scale OHLC by AdjClose/Close (dividends included)."""
    out = df.copy()
    if price_adjustment == "total_return" and "AdjClose" in out and out["Close"].notna().any():
        factor = out["AdjClose"] / out["Close"].replace(0, pd.NA)
        factor = factor.fillna(1.0)
        for c in OHLC:
            out[c] = out[c] * factor
    return out


def validate_and_prepare(df: pd.DataFrame, cfg):
    """Return (prepared_df, status, reason, warnings).

    status in {ok, insufficient_history}. Applies price adjustment, sanity checks.
    """
    warnings = []
    if df is None or len(df) == 0:
        return None, "insufficient_history", "empty", warnings

    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = apply_adjustment(df, cfg.data.price_adjustment)

    # Sanity: positive prices, High>=Low, increasing unique dates.
    if (df[OHLC] <= 0).any().any():
        warnings.append("non_positive_prices")
    if (df["High"] < df["Low"]).any():
        warnings.append("high_below_low")
    if not df.index.is_monotonic_increasing or df.index.duplicated().any():
        warnings.append("non_monotonic_dates")
    # Flag (don't crash on) unexplained single-day moves > 50%.
    if (df["Close"].pct_change().abs() > 0.50).sum() > 0:
        warnings.append("suspicious_single_day_move_gt50pct")

    weekly_bars = len(weekly(df))
    if len(df) < cfg.data.min_rows_daily or weekly_bars < cfg.weekly.min_weekly_bars_for_zone:
        return df, "insufficient_history", (
            f"rows={len(df)}(<{cfg.data.min_rows_daily}) "
            f"weekly={weekly_bars}(<{cfg.weekly.min_weekly_bars_for_zone})"
        ), warnings
    return df, "ok", "", warnings


def write_parquet(df: pd.DataFrame, path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = df.copy()
    frame.index.name = "date"
    table = pa.Table.from_pandas(frame.reset_index(), preserve_index=False)
    existing = dict(table.schema.metadata or {})
    for k, v in meta.items():
        existing[str(k).encode()] = str(v).encode()
    table = table.replace_schema_metadata(existing)
    pq.write_table(table, str(path))


def load_parquet(path: Path):
    """Return (df indexed by date, meta dict)."""
    table = pq.read_table(str(path))
    meta = {}
    if table.schema.metadata:
        for k, v in table.schema.metadata.items():
            try:
                meta[k.decode()] = v.decode()
            except Exception:
                pass
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df, meta


def write_manifest(rows: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=MANIFEST_COLUMNS).to_csv(path, index=False)


def read_manifest(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=MANIFEST_COLUMNS)
    return pd.read_csv(path, dtype={"symbol": str, "isin": str})


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

"""Storage + validation (blueprint 7 step 4/5, Appendix A).

Parquet per symbol with audit columns and file-level metadata
(symbol, isin, adjustment). Also manifest read/write.
"""
from __future__ import annotations

import json
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .indicators import weekly

MANIFEST_COLUMNS = [
    "symbol", "isin", "ticker", "source", "rows",
    "first_date", "last_date", "status", "fetched_at",
]

# Fixed in code (spec 7.5, closed bars only): the NSE regular session closes 15:30 IST.
IST = timezone(timedelta(hours=5, minutes=30))
NSE_CLOSE_IST = dt_time(15, 30)

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


def drop_filler_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop Yahoo's filler rows: zero volume and a flat bar at the previous close. Yahoo adds
    them on NSE holidays (and for days a thin stock did not trade); they are not sessions
    (spec 7.3: bars = trading sessions), and TradingView shows no bar for them."""
    if df is None or len(df) == 0:
        return df
    c = df["Close"]
    same = lambda a, b: np.isclose(a, b, rtol=1e-6, atol=0.0)  # float noise only; a real tick is far larger
    filler = ((df["Volume"] == 0) & same(df["Open"], c) & same(df["High"], c) & same(df["Low"], c)
              & same(c, c.shift(1)))
    return df[~filler]


def validate_and_prepare(df: pd.DataFrame, cfg):
    """Return (prepared_df, status, reason, warnings).

    status in {ok, insufficient_history}. Drops Yahoo filler rows, applies price
    adjustment, sanity checks.
    """
    warnings = []
    if df is None or len(df) == 0:
        return None, "insufficient_history", "empty", warnings

    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = drop_filler_rows(df)  # on raw prices, before any adjustment
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
    """Return (df indexed by date, meta dict). Filler rows are dropped here too, so data stored
    before that rule existed is read the same way (no re-download needed)."""
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
    return drop_filler_rows(df), meta


def prune_stale_parquets(daily_dir: Path, keep_symbols) -> list:
    """Delete data/daily/<SYM>.parquet whose symbol is NOT in keep_symbols.

    Keeps the on-disk store equal to the current universe so old/delisted/renamed
    or out-of-scope stocks don't accumulate. Only ever touches *.parquet files in
    daily_dir. Returns the sorted list of removed symbols.
    """
    keep = {str(s).strip().upper() for s in keep_symbols}
    removed = []
    if not daily_dir.exists():
        return removed
    for f in sorted(daily_dir.glob("*.parquet")):
        if f.stem.upper() not in keep:
            try:
                f.unlink()
                removed.append(f.stem)
            except OSError:
                pass
    return removed


def write_manifest(rows: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=MANIFEST_COLUMNS).to_csv(path, index=False)


def read_manifest(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=MANIFEST_COLUMNS)
    return pd.read_csv(path, dtype={"symbol": str, "isin": str})


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_close_utc(day) -> datetime:
    """The NSE close (15:30 IST) on calendar day `day`, as an aware UTC datetime."""
    d = pd.Timestamp(day).date()
    return datetime.combine(d, NSE_CLOSE_IST, tzinfo=IST).astimezone(timezone.utc)


def drop_forming_bar(df, fetched_at: datetime):
    """Spec 7.5: never store a still-forming daily candle. The newest bar is dropped
    when the download ran before that bar's own 15:30 IST close."""
    if df is None or len(df) == 0:
        return df
    if fetched_at < session_close_utc(df.index[-1]):
        return df.iloc[:-1]
    return df


def parse_fetched_at(value):
    """'2026-09-23T21:11:16Z' -> aware UTC datetime; blank/unparseable -> None."""
    if not value:
        return None
    try:
        ts = pd.Timestamp(value)
        return None if pd.isna(ts) else ts.tz_convert("UTC").to_pydatetime()
    except (ValueError, TypeError):
        return None


def session_closed_between(start_utc: datetime, end_utc: datetime) -> bool:
    """True if an NSE weekday close (15:30 IST) fell after start_utc and at/before end_utc.
    No holiday calendar: a holiday weekday counts too (worst case: one unneeded re-download)."""
    d = start_utc.astimezone(IST).date()
    last = end_utc.astimezone(IST).date()
    while d <= last:
        if d.weekday() < 5 and start_utc < session_close_utc(d) <= end_utc:
            return True
        d += timedelta(days=1)
    return False


def last_week_check(newest, now_utc: datetime, held_fn) -> dict:
    """Spec 7.5 under vendor lag (run by Step 1). `newest` = the newest bar ANY stock has.
    If that bar's W-FRI week is over by the clock (now >= its Friday 15:30 IST) but no stock
    has a bar on the week's later weekdays, ask NSE whether sessions were held on them:
    held_fn(day, now_utc) -> True (held) / False (no session) / None (unknown)."""
    newest = pd.Timestamp(newest).normalize()
    week = newest.to_period("W-FRI").end_time.normalize()  # that week's Friday label
    out = {"week": week.date().isoformat(), "cohort_newest": newest.date().isoformat(),
           "checked_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "sessions_missing": [], "unknown": []}
    if now_utc < session_close_utc(week) or newest >= week:
        return out  # week still forming, or its Friday bar is already in the data
    later = list(pd.bdate_range(newest + pd.Timedelta(days=1), week))
    if held_fn(newest, now_utc) is not True:  # probe: a day we have data for must be a session
        out["unknown"] = [d.date().isoformat() for d in later]  # NSE unreachable / renamed files
        return out
    for d in later:
        held = held_fn(d, now_utc)
        if held is True:
            out["sessions_missing"].append(d.date().isoformat())
        elif held is None:
            out["unknown"].append(d.date().isoformat())
    return out


def load_week_guard(manifest: pd.DataFrame, path: Path):
    """(guard, note) for Step 2's last-week closure. guard["cohort_newest"] = the newest bar any
    downloaded stock has; guard["incomplete_week"] = the W-FRI label of a week in which NSE held
    a session that no stock's data has yet. note = a report line when the NSE check found a
    missing session or could not run (then the cohort check + clock decide, with a warning)."""
    dates = pd.to_datetime(manifest.get("last_date"), errors="coerce").dropna()
    newest = dates.max() if len(dates) else None
    guard = {"cohort_newest": newest, "incomplete_week": None}
    if not path.exists():
        return guard, ""
    try:
        chk = json.loads(path.read_text(encoding="utf-8"))
        week, cohort = chk["week"], chk["cohort_newest"]
    except (ValueError, KeyError, TypeError, OSError):
        return guard, "NSE session check file unreadable: last weeks were closed by the clock and the cohort check only."
    if newest is None or cohort != newest.date().isoformat():
        return guard, ""  # the check belongs to an older download (Step 1 was interrupted): ignore it
    if chk.get("sessions_missing"):
        guard["incomplete_week"] = pd.Timestamp(week)
        return guard, (f"NSE held a session on {', '.join(chk['sessions_missing'])} that no stock's data "
                       f"has yet (Yahoo lag), so the week ending {week} stays PENDING. Re-run Step 1 "
                       f"later with refresh_if_older_than_hours = 0.")
    if chk.get("unknown"):
        return guard, (f"NSE session check unavailable for {', '.join(chk['unknown'])}: the week ending "
                       f"{week} was closed by the clock and the cohort check only (if Yahoo lags for "
                       f"every stock, that week's candle may be incomplete).")
    return guard, ""


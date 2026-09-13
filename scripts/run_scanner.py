#!/usr/bin/env python
"""Deliverable 2 — analyzer (blueprint 8, Appendix B). Thin entry point.

  python scripts/run_scanner.py

Reads the already-downloaded data/, computes indicators, applies the rules,
ranks the flagged set, and writes ONE output/top_recommended_for_<DATE>.txt per day
(summary folded in; optional CSV when [output] write_full_flagged_csv = true).
Re-runnable with no re-fetch after editing any [macd]..[output] setting.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src import store as storemod
from src import indicators as ind
from src import liquidity as liqmod
from src.divergence import detect_divergence
from src.zone import weekly_zone
from src import rank as rankmod
from src import report as reportmod


def _load_company_map(root: Path) -> dict:
    p = root / "data" / "universe" / "EQUITY_L.csv"
    if not p.exists():
        return {}
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
    except Exception:
        return {}
    sym_col = "symbol" if "symbol" in df.columns else ("SYMBOL" if "SYMBOL" in df.columns else None)
    name_col = "name" if "name" in df.columns else (
        "NAME OF COMPANY" if "NAME OF COMPANY" in df.columns else None)
    if not sym_col or not name_col:
        return {}
    return dict(zip(df[sym_col].str.strip(), df[name_col].str.strip()))


def analyze_symbol(sym: str, df: pd.DataFrame, isin: str, company: str, cfg):
    """Return ('flagged', record) | ('pending', sym) | ('skip', reason)."""
    n = len(df)
    weekly_bars = len(ind.weekly(df))
    if n < cfg.data.min_rows_daily or weekly_bars < cfg.weekly.min_weekly_bars_for_zone:
        return "skip", "insufficient_history"

    liq_ok, liq, last_close = liqmod.passes_liquidity(df, cfg)
    if not liq_ok:
        return "skip", "illiquid"

    H = ind.macd_hist(df["Close"], cfg.macd.fast, cfg.macd.slow, cfg.macd.signal)
    rsi = ind.rsi(df["Close"], cfg.rsi.period, cfg.rsi.smoothing)
    atr = ind.atr(df, 14)  # blueprint §8.1 pins ATR(14) regardless of the RSI period

    div = detect_divergence(df, H, cfg)
    if not div.is_true:
        return "skip", f"no_divergence:{div.reason}"

    zone = weekly_zone(df, div.swing_low_date, cfg)
    if zone.status == "pending_week":
        return "pending", sym
    if zone.status != "ok" or not zone.zone_ok:
        return "skip", f"zone:{zone.status if zone.status!='ok' else 'zone_fail'}"

    k = cfg.divergence.price_window_k
    lo = max(0, div.recent - k)
    hi = min(len(rsi) - 1, div.recent + k)
    rsi_trough = float(rsi.iloc[lo:hi + 1].min())
    rsi_check = "uncensored" if rsi_trough >= cfg.rsi.lower_band else "censored"

    atr14 = float(atr.iloc[-1])
    vol_recent = float(df["Volume"].iloc[div.recent])
    vol_median20 = float(df["Volume"].tail(20).median())
    bars_since_recent = (n - 1) - div.recent

    record = {
        "symbol": sym, "company": company or sym, "isin": isin or "",
        "h_prev": div.h_prev, "h_recent": div.h_recent,
        "pl_prev": div.pl_prev, "pl_recent": div.pl_recent,
        "prev_date": div.prev_date, "recent_date": div.recent_date,
        "swing_prev_date": div.swing_prev_date, "swing_recent_date": div.swing_low_date,
        "momentum_ok": div.momentum_ok, "price_ok": div.price_ok, "confirmed": div.confirmed,
        "W": zone.W, "ema_vals": dict(zone.emas),
        "band_lo": zone.band_lo, "band_hi": zone.band_hi, "band_mid": zone.band_mid,
        "band_close_w": zone.week_close, "week_low": zone.week_low,
        "week_high": zone.week_high, "week_close": zone.week_close, "zone_ok": zone.zone_ok,
        "rsi_trough": rsi_trough, "rsi_check": rsi_check,
        "liquidity": liq, "last_close": last_close, "atr14": atr14,
        "vol_recent": vol_recent, "vol_median20": vol_median20,
        "bars_since_recent": bars_since_recent, "recency_bars": cfg.divergence.recency_bars,
        "last_date": df.index.max(),
    }
    return "flagged", record


def main() -> int:
    cfg = load_config()
    root = cfg.project_root
    data_dir = root / "data"
    daily_dir = data_dir / "daily"
    out_dir = root / cfg.output.dir

    manifest = storemod.read_manifest(data_dir / "manifest.csv")
    if manifest.empty:
        print("[scan] no manifest - run scripts/fetch_data.py first", flush=True)
        return 1

    company_map = _load_company_map(root)
    ok = manifest[manifest["status"] == "ok"]

    def emit(msg):
        print(msg, flush=True)

    emit(f"[scan] analyzing {len(ok)} ok symbols (of {len(manifest)} in manifest)")

    flagged = []
    pending = []
    skip_reasons = {}
    n_scanned = 0
    n_liquid = 0
    last_dates = []

    for row in ok.itertuples(index=False):
        sym = row.symbol
        pq_path = daily_dir / f"{sym}.parquet"
        if not pq_path.exists():
            skip_reasons["missing_parquet"] = skip_reasons.get("missing_parquet", 0) + 1
            continue
        try:
            df, meta = storemod.load_parquet(pq_path)
        except Exception as e:  # noqa: BLE001 — one bad symbol never aborts
            emit(f"[scan] {sym}: load error {e}")
            skip_reasons["load_error"] = skip_reasons.get("load_error", 0) + 1
            continue

        n_scanned += 1
        last_dates.append(df.index.max())
        isin = meta.get("isin", "") or (getattr(row, "isin", "") or "")
        company = company_map.get(sym, sym)

        try:
            kind, payload = analyze_symbol(sym, df, isin, company, cfg)
        except Exception as e:  # noqa: BLE001
            emit(f"[scan] {sym}: analysis error {e}")
            skip_reasons["analysis_error"] = skip_reasons.get("analysis_error", 0) + 1
            continue

        if kind == "flagged":
            flagged.append(payload)
            n_liquid += 1  # flagged always passed the liquidity filter
            emit(f"[scan] {sym}: FLAGGED (rsi {payload['rsi_check']}, "
                 f"liq Rs{payload['liquidity']/1e7:.1f}cr)")
        elif kind == "pending":
            pending.append(payload)
            n_liquid += 1  # pending passed liquidity; only the weekly candle is unconfirmed
        else:
            skip_reasons[payload] = skip_reasons.get(payload, 0) + 1
            # count as "passed liquidity" ONLY if it cleared both the history gate and the
            # liquidity filter (i.e. failed a later criterion) — never insufficient_history/illiquid
            if payload not in ("illiquid", "insufficient_history"):
                n_liquid += 1

    ranked = rankmod.rank(flagged, cfg)

    as_of = max(last_dates).date().isoformat() if last_dates else "unknown"
    failed_syms = manifest[manifest["status"] == "failed"]["symbol"].tolist()
    meta = {
        "date": as_of,
        "generated": reportmod.now_ist(),
        "U": n_scanned,
        "L": n_liquid,
        "F": len(flagged),
        "P": len(pending),
        "skips": skip_reasons,
        "failed_symbols": failed_syms,
    }

    print(f"[scan] as-of {as_of}: scanned={n_scanned} flagged={len(flagged)} "
          f"pending={len(pending)}", flush=True)
    for reason, cnt in sorted(skip_reasons.items(), key=lambda x: -x[1]):
        print(f"[scan] skip {reason}: {cnt}", flush=True)

    # ONE report file per day (overwritten on re-run); summary is folded in.
    paths = reportmod.write_outputs(ranked, pending, meta, cfg, out_dir)
    print(f"[scan] wrote {paths['report']}", flush=True)
    if "csv" in paths:
        print(f"[scan] wrote {paths['csv']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Deliverable 1 - data fetcher (blueprint 7). Thin entry point.

  python scripts/fetch_data.py

Downloads ~6y split-adjusted daily OHLCV for the configured universe into
data/daily/<SYMBOL>.parquet and writes data/manifest.csv. Resumable,
throttled, one bad symbol never aborts. Startup smoke-fetch aborts loudly on
Yahoo/yfinance shape drift.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make src importable from anywhere, on Linux and Windows.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src import fetch as fetchmod
from src import store as storemod
from src import universe as universemod

# Fixed in code (blueprint 6): dirs + bhavcopy-failover log threshold.
BHAVCOPY_FAILOVER_THRESHOLD = 0.05  # >5% *failed* (not insufficient) -> recommend bhavcopy tail


def _fresh(path: Path, hours: float) -> bool:
    if hours <= 0 or not path.exists():
        return False
    age_h = (time.time() - path.stat().st_mtime) / 3600.0
    return age_h < hours


def main() -> int:
    cfg = load_config()
    root = cfg.project_root
    data_dir = root / "data"
    daily_dir = data_dir / "daily"
    universe_dir = data_dir / "universe"
    daily_dir.mkdir(parents=True, exist_ok=True)

    log = []

    def emit(msg):
        print(msg, flush=True)
        log.append(msg)

    emit(f"[fetch] start {datetime.now(timezone.utc).isoformat()}  root={root}")

    # 1) Startup smoke-fetch - abort loudly on drift.
    try:
        fetchmod.smoke_fetch(cfg.data.history_years)
        emit("[fetch] smoke-fetch OK")
    except Exception as e:  # noqa: BLE001
        emit(f"[fetch] FATAL smoke-fetch failed: {e}")
        return 2

    # 2) Universe.
    try:
        uni = universemod.build_universe(cfg)
    except Exception as e:  # noqa: BLE001
        emit(f"[fetch] FATAL could not build universe: {e}")
        return 3
    prev = universemod.save_snapshot(uni, universe_dir)
    diff = universemod.diff_universe(prev, uni)
    emit(f"[fetch] universe: {len(uni)} symbols "
         f"(renamed={len(diff['renamed'])} added={len(diff['added'])} dropped={len(diff['dropped'])})")
    for old, new, isin in diff["renamed"]:
        emit(f"[fetch]   RENAME {old} -> {new} (isin {isin})")

    # 3) Fetch loop.
    manifest_rows = []
    counts = {"ok": 0, "insufficient_history": 0, "failed": 0}
    failed_syms = []
    t0 = time.time()
    total = len(uni)
    for i, row in enumerate(uni.itertuples(index=False), 1):
        sym = row.symbol
        isin = getattr(row, "isin", "")
        pq_path = daily_dir / f"{sym}.parquet"

        if _fresh(pq_path, cfg.data.refresh_if_older_than_hours):
            try:
                df_prev, meta_prev = storemod.load_parquet(pq_path)
                counts[meta_prev.get("status", "ok")] = counts.get(meta_prev.get("status", "ok"), 0) + 1
                manifest_rows.append({
                    "symbol": sym, "isin": isin, "ticker": f"{sym}.NS",
                    "source": meta_prev.get("source", "cache"), "rows": len(df_prev),
                    "first_date": df_prev.index.min().date().isoformat(),
                    "last_date": df_prev.index.max().date().isoformat(),
                    "status": meta_prev.get("status", "ok"),
                    "fetched_at": meta_prev.get("fetched_at", ""),
                })
                emit(f"[{i}/{total}] {sym:<14} CACHED ({len(df_prev)} rows)")
                continue
            except Exception:
                pass  # cache unreadable -> refetch

        try:
            raw, source = fetchmod.fetch_symbol(sym, cfg.data.history_years)
            df, status, reason, warns = storemod.validate_and_prepare(raw, cfg)
            fetched_at = storemod.utcnow_iso()
            if df is not None:
                storemod.write_parquet(df, pq_path, {
                    "symbol": sym, "isin": isin, "adjustment": cfg.data.price_adjustment,
                    "source": source, "status": status, "fetched_at": fetched_at,
                })
            counts[status] = counts.get(status, 0) + 1
            rows_n = 0 if df is None else len(df)
            fd = df.index.min().date().isoformat() if (df is not None and len(df)) else ""
            ld = df.index.max().date().isoformat() if (df is not None and len(df)) else ""
            manifest_rows.append({
                "symbol": sym, "isin": isin, "ticker": f"{sym}.NS", "source": source,
                "rows": rows_n, "first_date": fd, "last_date": ld,
                "status": status, "fetched_at": fetched_at,
            })
            wmsg = f" warn={warns}" if warns else ""
            emit(f"[{i}/{total}] {sym:<14} {status:<20} rows={rows_n} src={source}{reason and ' '+reason or ''}{wmsg}")
        except Exception as e:  # noqa: BLE001 - one bad symbol never aborts
            counts["failed"] += 1
            failed_syms.append(sym)
            manifest_rows.append({
                "symbol": sym, "isin": isin, "ticker": f"{sym}.NS", "source": "none",
                "rows": 0, "first_date": "", "last_date": "",
                "status": "failed", "fetched_at": storemod.utcnow_iso(),
            })
            emit(f"[{i}/{total}] {sym:<14} FAILED {e.__class__.__name__}: {e}")

        time.sleep(cfg.data.request_throttle_sec)

    # 4/5) Manifest + summary.
    storemod.write_manifest(manifest_rows, data_dir / "manifest.csv")
    dt = time.time() - t0
    emit(f"[fetch] done in {dt:.0f}s "
         f"ok={counts['ok']} insufficient_history={counts['insufficient_history']} failed={counts['failed']}")

    # B2: failover threshold on FAILED only; cross-check failed set is logged.
    denom = max(counts["ok"] + counts["failed"], 1)
    fail_rate = counts["failed"] / denom
    emit(f"[fetch] REAL failure rate (failed / (ok+failed)) = {fail_rate*100:.1f}%")
    if failed_syms:
        emit(f"[fetch] FAILED symbols (cross-check vs liquidity/index): {', '.join(failed_syms)}")
    if fail_rate > BHAVCOPY_FAILOVER_THRESHOLD:
        emit(f"[fetch] WARNING failed rate > {BHAVCOPY_FAILOVER_THRESHOLD*100:.0f}% "
             f"-> consider bhavcopy failover for the tail.")

    (data_dir / "fetch_log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

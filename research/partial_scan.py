"""Partial scan over whatever is ALREADY in data/daily/ (does not wait for the
full fetch, does not touch manifest.csv or the running fetch). Reuses the exact
production pipeline (src + scripts/run_scanner.analyze_symbol) so results are the
same criteria, truthful. Writes a clearly-labelled PARTIAL report.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.config import load_config
from src import store as storemod
from src import rank as rankmod
from src import report as reportmod
import run_scanner


def main() -> int:
    cfg = load_config()
    root = cfg.project_root
    daily = root / "data" / "daily"
    company_map = run_scanner._load_company_map(root)

    parquets = sorted(daily.glob("*.parquet"))
    flagged, pending, skip = [], [], {}
    n_scanned, n_liquid, last_dates = 0, 0, []

    for pq in parquets:
        sym = pq.stem
        try:
            df, m = storemod.load_parquet(pq)
        except Exception:
            skip["load_error"] = skip.get("load_error", 0) + 1
            continue
        n_scanned += 1
        last_dates.append(df.index.max())
        isin = m.get("isin", "")
        company = company_map.get(sym, sym)
        try:
            kind, payload = run_scanner.analyze_symbol(sym, df, isin, company, cfg)
        except Exception as e:  # noqa: BLE001
            skip["analysis_error"] = skip.get("analysis_error", 0) + 1
            continue
        if kind == "flagged":
            flagged.append(payload)
            n_liquid += 1
        elif kind == "pending":
            pending.append(payload)
            n_liquid += 1
        else:
            skip[payload] = skip.get(payload, 0) + 1
            if payload not in ("illiquid", "insufficient_history"):
                n_liquid += 1

    ranked = rankmod.rank(flagged, cfg)
    as_of = max(last_dates).date().isoformat() if last_dates else "unknown"
    meta = {"date": as_of, "generated": reportmod.now_ist(),
            "U": n_scanned, "L": n_liquid, "F": len(flagged), "P": len(pending)}

    text = reportmod.build_report_text(ranked, pending, meta, cfg)
    out = root / "output" / f"top_recommended_PARTIAL_{n_scanned}syms_{as_of}.txt"
    out.write_text(text, encoding="utf-8")

    print(f"[partial] scanned={n_scanned} liquid_pass={n_liquid} "
          f"FLAGGED={len(flagged)} pending={len(pending)}")
    print("[partial] skip reasons: " + ", ".join(f"{k}={v}" for k, v in
          sorted(skip.items(), key=lambda x: -x[1])))
    print(f"[partial] wrote {out}")
    print("\n[partial] ALL FLAGGED (ranked):")
    for r in ranked:
        print(f"   #{r['rank']:>2}  {r['symbol']:<12} score {r['score']:+.2f}  "
              f"{r['rsi_check']:<10} liq Rs{r['liquidity']/1e7:.0f}cr  zone-wk {r['W'].date()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

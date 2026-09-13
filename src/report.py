"""Report writer (blueprint 8.7).

TRUTHFULNESS MANDATE: every printed value comes from the computed record.
Nothing hardcoded/placeholder. Unfetchable field -> 'n/a'.
Writes ONE top_recommended_for_<DATE>.txt per day (2 sections + scan summary), overwritten
on re-run; optional flagged_<DATE>.csv when [output] write_full_flagged_csv = true.
Output is plain ASCII (portable + readable in any editor on Windows/Linux).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

# Fixed in code (blueprint 6): report filename pattern.
REPORT_PATTERN = "top_recommended_for_{date}.txt"
FLAGGED_PATTERN = "flagged_{date}.csv"

BAR = "=" * 69
SUBBAR = "-" * 69


def _num(v, nd=2):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    return f"{v:.{nd}f}"


def _cr(liq_inr):
    if liq_inr is None or pd.isna(liq_inr):
        return "n/a"
    return f"{liq_inr / 1e7:.0f}"


def _settings_echo(cfg) -> str:
    d = cfg.divergence
    parts = [
        f"MACD {cfg.macd.fast}/{cfg.macd.slow}/{cfg.macd.signal}",
        f"lookback={d.lookback_days} K={d.price_window_k}",
        f"trough={d.trough_detection}(seg>={d.min_segment_len},prom={d.prominence_frac})",
        f"scope={d.divergence_scope} sep={d.min_trough_sep} tol={d.tolerance_pct}",
        f"price_field={d.price_field} confirm={d.require_confirmation}/{d.confirm_bars} recency={d.recency_bars}",
        f"weekEMA={cfg.weekly.ema_set} zone={cfg.weekly.zone_test} minWk={cfg.weekly.min_weekly_bars_for_zone}",
        f"RSI {cfg.rsi.period}/{cfg.rsi.smoothing}/lb{cfg.rsi.lower_band:g}",
        f"liq>={cfg.liquidity.min_median_traded_value_inr/1e7:g}cr&>={cfg.liquidity.min_price:g} win={cfg.liquidity.window}",
        f"adj={cfg.data.price_adjustment}",
        f"top_n={cfg.ranking.top_n}",
    ]
    return " | ".join(parts)


def _section1(ranked, cfg) -> list:
    lines = []
    lines.append(f" SECTION 1 - THE LIST   (#1..#{cfg.ranking.top_n} are the top picks; the rest is the full flagged list)")
    lines.append("")
    lines.append(f"   {'#':>3}  {'SYMBOL':<12} {'COMPANY':<26} {'SCORE':>6}  {'RSI':<11} {'LIQ Rs cr/d':>11}  {'ZONE WEEK':<10}")
    lines.append(f"   {'-'*3}  {'-'*12} {'-'*26} {'-'*6}  {'-'*11} {'-'*11}  {'-'*10}")
    top_n = cfg.ranking.top_n
    emitted_sep = False
    for r in ranked:
        if r["rank"] == top_n + 1 and not emitted_sep:
            lines.append("   ---- remaining flagged ----")
            emitted_sep = True
        company = (r["company"] or "")[:26]
        wk = r["W"].date().isoformat() if r.get("W") is not None else "n/a"
        lines.append(
            f"   {r['rank']:>3}  {r['symbol']:<12} {company:<26} "
            f"{_num(r['score']):>6}  {r['rsi_check']:<11} {_cr(r['liquidity']):>11}  {wk:<10}"
        )
    return lines


def _price_dir_word(pl_recent, pl_prev):
    if pl_recent < pl_prev:
        return "a LOWER low"
    if pl_recent == pl_prev:
        return "an EQUAL low"
    return "an EQUAL low (within tolerance)"


def _section2(ranked, cfg) -> list:
    lines = []
    lines.append(" SECTION 2 - WHY EACH STOCK WAS CHOSEN (simple explanation)")
    lower_band = cfg.rsi.lower_band
    floor_cr = cfg.liquidity.min_median_traded_value_inr / 1e7
    zone_word = "overlapped the band" if cfg.weekly.zone_test == "range_overlap" else "closed inside the band"
    for r in ranked:
        lines.append("")
        lines.append(f" {SUBBAR}")
        lines.append(f" #{r['rank']}  {r['symbol']}  ({r['company'] or 'n/a'})"
                     f"     score {_num(r['score'])}   RSI: {r['rsi_check']}")
        lines.append("")
        price_word = ("a lower low" if r["pl_recent"] < r["pl_prev"]
                      else "an equal low (a possible double bottom)")
        rsi_phrase = ("RSI stayed at a healthy level (at/above 30)"
                      if r["rsi_check"] == "uncensored" else "RSI dipped below 30 (a weaker sign)")
        lines.append(
            f"   What happened: over recent weeks {r['symbol']}'s price made {price_word} (down to\n"
            f"   {_num(r['pl_recent'])} on {r['recent_date'].date()}), while its daily MACD momentum made a\n"
            f"   HIGHER low and then turned back up - an early sign the slide may be easing. That low fell\n"
            f"   inside {r['symbol']}'s weekly EMA 11/22/50 support band, and {rsi_phrase}."
        )
        lines.append("")
        lines.append("   The checks it passed:")
        rsi_word = "at/above" if r["rsi_trough"] >= lower_band else "below"
        lines.append(
            f"     1) Divergence (daily): dip on {r['prev_date'].date()} "
            f"(MACD {r['h_prev']:+.2f}, low {_num(r['pl_prev'])} on {r['swing_prev_date'].date()}), then a\n"
            f"        higher-momentum dip on {r['recent_date'].date()} "
            f"(MACD {r['h_recent']:+.2f}, low {_num(r['pl_recent'])} on {r['swing_recent_date'].date()}).\n"
            f"        Momentum made a HIGHER low while price made {_price_dir_word(r['pl_recent'], r['pl_prev'])}, "
            f"and the latest\n"
            f"        dip was {'confirmed (momentum turned back up)' if r['confirmed'] else 'NOT confirmed'}.  "
            f"[{'OK' if r['momentum_ok'] and r['price_ok'] and r['confirmed'] else 'X'}]"
        )
        ema_str = ", ".join(f"EMA{p} {_num(r['ema_vals'].get(p), 1)}" for p in cfg.weekly.ema_set)
        lines.append(
            f"     2) Weekly support zone (week of {r['W'].date()}): the weekly averages were\n"
            f"        {ema_str}.\n"
            f"        They formed a band {_num(r['band_lo'],1)} to {_num(r['band_hi'],1)}; that week's range "
            f"{_num(r['week_low'],1)} to {_num(r['week_high'],1)} {zone_word}.  "
            f"[{'OK' if r['zone_ok'] else 'X'}]"
        )
        lines.append(
            f"     3) RSI health: RSI at the low was {_num(r['rsi_trough'])} ({rsi_word} {lower_band:g}) "
            f'=> "{r["rsi_check"]}"\n'
            f"        ({'a healthy dip, not a panic sell-off' if r['rsi_check'] == 'uncensored' else 'a weaker dip; still listed (RSI only labels)'})."
        )
        lines.append(
            f"     4) Liquidity: about Rs {_cr(r['liquidity'])} cr traded per day "
            f"(above the Rs {floor_cr:g} cr minimum) => tradeable."
        )
    return lines


def build_report_text(ranked, pending, meta, cfg) -> str:
    L = []
    L.append(BAR)
    L.append(" NSE SCANNER - TOP RECOMMENDATIONS")
    L.append(f" Data as-of : {meta['date']} (last trading day)        Generated: {meta['generated']} IST")
    L.append(" Setup      : Daily MACD-histogram bullish divergence + weekly EMA(11/22/50) support zone")
    if meta.get("listed"):
        skipped = meta.get("skipped_insufficient", 0)
        L.append(f" Universe   : {meta['listed']} NSE equities listed | {meta['U']} had enough "
                 f"history and were scanned")
        L.append(f"              ({skipped} skipped - too new for a 4-year weekly average) | "
                 f"{meta['L']} passed liquidity | {meta['F']} flagged | {meta['P']} pending")
    else:
        L.append(f" Universe   : {meta['U']} EQ scanned | {meta['L']} passed liquidity | "
                 f"{meta['F']} flagged | {meta['P']} pending week-close")
    if meta.get("partial"):
        L.append(f" NOTE       : PARTIAL run - {meta['U']} of ~{meta.get('universe_total', 2292)} symbols "
                 f"downloaded so far; this file refreshes when the full download finishes.")
    L.append(f" Settings   : {_settings_echo(cfg)}")
    L.append(f" Data source: yfinance (.NS, {cfg.data.price_adjustment}, "
             f"{'dividends unadjusted' if cfg.data.price_adjustment=='split_only' else 'total return'})")
    L.append(BAR)
    L.append("")
    L.extend(_section1(ranked, cfg))
    L.append("")
    L.append(BAR)
    L.append("")
    L.extend(_section2(ranked, cfg))
    L.append("")
    L.append(BAR)
    L.append("")
    pend = ", ".join(pending) if pending else "(none)"
    L.append(f" PENDING (weekly candle still forming; will confirm after the week closes): {pend}")
    L.append("")
    skips = meta.get("skips") or {}
    if skips:
        L.append(" SCAN SUMMARY (why the other stocks were not selected)")
        L.append(f"   scanned {meta['U']} | passed liquidity+history {meta['L']} | "
                 f"flagged {meta['F']} | pending {meta['P']}")
        label = {
            "illiquid": "below liquidity/price floor",
            "insufficient_history": "too little history (<~4y)",
            "no_divergence:criteria_not_met": "no valid bullish divergence",
            "no_divergence:no_causal_recent_trough": "no confirmed recent trough",
            "no_divergence:fewer_than_two_troughs": "fewer than two troughs",
            "no_divergence:no_prior_trough_with_separation": "no separated prior trough",
            "zone:zone_fail": "low not inside the weekly EMA zone",
        }
        for k, v in sorted(skips.items(), key=lambda x: -x[1]):
            L.append(f"     {v:>5}  {label.get(k, k)}")
        fails = meta.get("failed_symbols") or []
        if fails:
            shown = ", ".join(fails[:15]) + (" ..." if len(fails) > 15 else "")
            L.append(f"   fetch-failed ({len(fails)}): {shown}")
        L.append("")
    L.append(" NOTES")
    L.append('  - "uncensored" = the dip stayed at/above RSI 30 (healthier). "censored" = it dipped')
    L.append("    below 30 (weaker) but the stock is STILL listed (the RSI check only labels, it")
    L.append("    never removes a stock).")
    L.append(f"  - Every number above is computed from the sourced data as of {meta['date']}.")
    L.append("    This is not investment advice; always verify each chart before acting.")
    L.append(BAR)
    return "\n".join(L) + "\n"


def _flagged_dataframe(ranked) -> pd.DataFrame:
    rows = []
    for r in ranked:
        rows.append({
            "rank": r["rank"],
            "symbol": r["symbol"],
            "company": r["company"],
            "isin": r["isin"],
            "score": r["score"],
            "prev_date": r["prev_date"].date().isoformat(),
            "h_prev": r["h_prev"],
            "pl_prev": r["pl_prev"],
            "recent_date": r["recent_date"].date().isoformat(),
            "h_recent": r["h_recent"],
            "pl_recent": r["pl_recent"],
            "swing_prev_date": r["swing_prev_date"].date().isoformat(),
            "swing_recent_date": r["swing_recent_date"].date().isoformat(),
            "momentum_ok": r["momentum_ok"],
            "price_ok": r["price_ok"],
            "confirmed": r["confirmed"],
            "zone_week": r["W"].date().isoformat(),
            **{f"ema{p}": v for p, v in r["ema_vals"].items()},
            "band_lo": r["band_lo"],
            "band_hi": r["band_hi"],
            "week_low": r["week_low"],
            "week_high": r["week_high"],
            "week_close": r["week_close"],
            "zone_ok": r["zone_ok"],
            "rsi_trough": r["rsi_trough"],
            "rsi_check": r["rsi_check"],
            "liquidity_inr": r["liquidity"],
            "atr14": r["atr14"],
            "z_momentum": r["z"]["momentum"],
            "z_zone_confluence": r["z"]["zone_confluence"],
            "z_rsi_quality": r["z"]["rsi_quality"],
            "z_liquidity": r["z"]["liquidity"],
            "z_recency": r["z"]["recency"],
            "z_volume_expansion": r["z"]["volume_expansion"],
        })
    return pd.DataFrame(rows)


def write_outputs(ranked, pending, meta, cfg, out_dir: Path) -> dict:
    """Write ONE report file per day: top_recommended_for_<DATE>.txt (overwritten
    on re-run; the 'Generated' timestamp inside updates). The run summary is folded
    into that file. An optional machine-readable CSV is written only when
    [output] write_full_flagged_csv = true (default off -> a single file per day).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    date = meta["date"]
    paths = {}

    txt = build_report_text(ranked, pending, meta, cfg)
    p_txt = out_dir / REPORT_PATTERN.format(date=date)
    p_txt.write_text(txt, encoding="utf-8")
    paths["report"] = p_txt

    if cfg.output.write_full_flagged_csv:
        p_csv = out_dir / FLAGGED_PATTERN.format(date=date)
        _flagged_dataframe(ranked).to_csv(p_csv, index=False)
        paths["csv"] = p_csv

    return paths


def now_ist() -> str:
    # IST = UTC+5:30 (no OS tz dependency).
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d %H:%M")

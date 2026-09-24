"""Report writer (blueprint 8.7).

TRUTHFULNESS MANDATE: every printed value comes from the computed record.
Nothing hardcoded/placeholder. Unfetchable field -> 'n/a'.
Writes ONE top_recommended_for_<DATE>.txt per day (2 sections + scan summary), overwritten
on re-run; optional flagged_<DATE>.csv when [output] write_full_flagged_csv = true.
Output is plain ASCII (portable + readable in any editor on Windows/Linux).
"""
from __future__ import annotations

import textwrap
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


def _h(v):
    """MACD-histogram value: 2 decimals, or 4 below 1 so a small dip never prints as -0.00."""
    if v is None or pd.isna(v):
        return "n/a"
    return f"{v:+.2f}" if abs(v) >= 1 else f"{v:+.4f}"


def _lvl(v):
    """A price-level average (EMA/band): 1 decimal from 100, 2 from 10, else 3 (low-priced stocks)."""
    if v is None or pd.isna(v):
        return "n/a"
    return _num(v, 1 if abs(v) >= 100 else 2 if abs(v) >= 10 else 3)


def _cr(liq_inr):
    if liq_inr is None or pd.isna(liq_inr):
        return "n/a"
    return f"{liq_inr / 1e7:.0f}"


def _data_to(r, as_of) -> str:
    """' (data to YYYY-MM-DD)' when this stock's data ends before/after the report's as-of date."""
    d = r.get("last_date")
    if d is None or pd.Timestamp(d).date().isoformat() == as_of:
        return ""
    return f" (data to {pd.Timestamp(d).date().isoformat()})"


def _settings_echo(cfg) -> str:
    d = cfg.divergence
    parts = [
        f"MACD {cfg.macd.fast}/{cfg.macd.slow}/{cfg.macd.signal}",
        f"lookback={d.lookback_days} pivotK={d.trough_pivot_k} K={d.price_window_k}",
        f"tol={d.tolerance_pct} price_field={d.price_field}",
        f"weekEMA={cfg.weekly.ema_set} zone={cfg.weekly.zone_test} minWk={cfg.weekly.min_weekly_bars_for_zone} minDays={cfg.data.min_rows_daily}",
        f"RSI {cfg.rsi.period}/{cfg.rsi.smoothing}/lb{cfg.rsi.lower_band:g}",
        f"liq>={cfg.liquidity.min_median_traded_value_inr/1e7:g}cr&>={cfg.liquidity.min_price:g} win={cfg.liquidity.window}",
        f"adj={cfg.data.price_adjustment}",
        f"top_n={cfg.ranking.top_n}",
    ]
    return " | ".join(parts)


def _section1(ranked, cfg, as_of="") -> list:
    lines = []
    rest = "every other setup that passes liquidity" if cfg.liquidity.apply_as_filter else "every other setup"
    lines.append(f" SECTION 1 - THE LIST   (#1..#{cfg.ranking.top_n} are the top picks, then {rest})")
    lines.append("   PREV DIP / RECENT DIP = the two MACD-histogram trough dates; ZONE WK = start of the weekly EMA-zone candle")
    lines.append("")
    lines.append(f"   {'#':>3}  {'SYMBOL':<12} {'COMPANY':<20} {'SCORE':>6}  {'RSI':<11} "
                 f"{'PREV DIP':<10} {'RECENT DIP':<10} {'ZONE WK':<10} {'LIQ cr/d':>8}")
    lines.append(f"   {'-'*3}  {'-'*12} {'-'*20} {'-'*6}  {'-'*11} {'-'*10} {'-'*10} {'-'*10} {'-'*8}")
    top_n = cfg.ranking.top_n
    emitted_sep = False
    for r in ranked:
        if r["rank"] == top_n + 1 and not emitted_sep:
            lines.append("   ---- other tradeable setups ----")
            emitted_sep = True
        company = (r["company"] or "")[:20]
        pv = r["prev_date"].date().isoformat() if r.get("prev_date") is not None else "n/a"
        rc = r["recent_date"].date().isoformat() if r.get("recent_date") is not None else "n/a"
        wk = r["week_start"].date().isoformat() if r.get("week_start") is not None else "n/a"
        lines.append(
            f"   {r['rank']:>3}  {r['symbol']:<12} {company:<20} "
            f"{_num(r['score']):>6}  {r['rsi_check']:<11} {pv:<10} {rc:<10} {wk:<10} {_cr(r['liquidity']):>8}"
            f"{_data_to(r, as_of)}"
        )
    return lines


def _price_dir_word(pl_recent, pl_prev):
    if pl_recent < pl_prev:
        return "a LOWER low"
    if pl_recent == pl_prev:
        return "an EQUAL low"
    return "an EQUAL low (within tolerance)"


def _section2(ranked, cfg, as_of="") -> list:
    lines = []
    lines.append(" SECTION 2 - WHY EACH STOCK WAS CHOSEN (simple explanation)")
    lower_band = cfg.rsi.lower_band
    k = cfg.divergence.price_window_k
    floor_cr = cfg.liquidity.min_median_traded_value_inr / 1e7
    min_px = cfg.liquidity.min_price
    zone_word = "overlapped the band" if cfg.weekly.zone_test == "range_overlap" else "closed inside the band"
    # spec 3.2 tests the swing-low WEEK's candle against the band, not the low itself.
    zone_sentence = ("That week's price range touched" if cfg.weekly.zone_test == "range_overlap"
                     else "That week closed inside")
    emas = "/".join(str(p) for p in cfg.weekly.ema_set)
    for r in ranked:
        lines.append("")
        lines.append(f" {SUBBAR}")
        lines.append(f" #{r['rank']}  {r['symbol']}  ({r['company'] or 'n/a'})"
                     f"     score {_num(r['score'])}   RSI: {r['rsi_check']}{_data_to(r, as_of)}")
        lines.append("")
        price_word = ("a lower low" if r["pl_recent"] < r["pl_prev"]
                      else "an equal low (a possible double bottom)")
        rsi_phrase = (f"RSI stayed at/above {lower_band:g} around the dip (healthy)"
                      if r["rsi_check"] == "uncensored" else f"RSI dipped below {lower_band:g} around the dip (a weaker sign)")
        lines.append(
            f"   What happened: over recent weeks {r['symbol']}'s price made {price_word} (down to\n"
            f"   {_num(r['pl_recent'])} on {r['swing_recent_date'].date()}), while its daily MACD momentum made a\n"
            f"   HIGHER low - an early sign the slide may be easing. {zone_sentence}\n"
            f"   {r['symbol']}'s weekly EMA {emas} support band, and {rsi_phrase}."
        )
        lines.append("")
        lines.append("   The checks it passed:")
        rsi_word = "at/above" if r["rsi_trough"] >= lower_band else "below"
        lines.append(
            f"     1) Divergence (daily): dip on {r['prev_date'].date()} "
            f"(MACD {_h(r['h_prev'])}, low {_num(r['pl_prev'])} on {r['swing_prev_date'].date()}), then a\n"
            f"        higher-momentum dip on {r['recent_date'].date()} "
            f"(MACD {_h(r['h_recent'])}, low {_num(r['pl_recent'])} on {r['swing_recent_date'].date()}).\n"
            f"        Momentum made a HIGHER low while price made {_price_dir_word(r['pl_recent'], r['pl_prev'])}.  "
            f"[{'OK' if r['momentum_ok'] and r['price_ok'] else 'X'}]"
        )
        ema_str = ", ".join(f"EMA{p} {_lvl(r['ema_vals'].get(p))}" for p in cfg.weekly.ema_set)
        lines.append(
            f"     2) Weekly support zone (week of {r['week_start'].date()}): the weekly averages were\n"
            f"        {ema_str}.\n"
            f"        They formed a band {_lvl(r['band_lo'])} to {_lvl(r['band_hi'])}; that week's range "
            f"{_lvl(r['week_low'])} to {_lvl(r['week_high'])} {zone_word}.  "
            f"[{'OK' if r['zone_ok'] else 'X'}]"
        )
        lines.append(
            f"     3) RSI health: the lowest RSI within {k} days of the MACD dip was {_num(r['rsi_trough'])} "
            f"({rsi_word} {lower_band:g}) "
            f'=> "{r["rsi_check"]}"\n'
            f"        ({'a healthy dip, not a panic sell-off' if r['rsi_check'] == 'uncensored' else 'a weaker dip; still listed (RSI only labels)'})."
        )
        below = []
        if not r["liquidity"] >= cfg.liquidity.min_median_traded_value_inr:  # NaN-safe
            below.append(f"the Rs {floor_cr:g} cr/day minimum")
        if not r["last_close"] >= min_px:
            below.append(f"the Rs {min_px:g} price minimum")
        if below:  # only possible when [liquidity] apply_as_filter = false
            lines.append(
                f"     4) Liquidity: about Rs {_cr(r['liquidity'])} cr traded per day, below "
                f"{' and '.join(below)} => below the liquidity/price floor (listed only because the "
                f"liquidity filter is off)."
            )
        else:
            lines.append(
                f"     4) Liquidity: about Rs {_cr(r['liquidity'])} cr traded per day "
                f"(above the Rs {floor_cr:g} cr minimum) => tradeable."
            )
    return lines


def _illiquid_reason(x, cfg, as_of="") -> str:
    """Why a spec pass failed liquidity: turnover under the floor and/or price under the minimum."""
    parts = []
    liq, px = x["liquidity"], x["last_close"]
    if not liq >= cfg.liquidity.min_median_traded_value_inr:  # NaN-safe: missing turnover fails too
        parts.append(f"Rs {liq / 1e7:.2f} cr/d" if pd.notna(liq) else "turnover n/a")
    if not px >= cfg.liquidity.min_price:
        parts.append(f"price Rs {px:.2f}" if pd.notna(px) else "price n/a")
    return f"{x['symbol']} ({', '.join(parts)}){_data_to(x, as_of)}"


def build_report_text(ranked, pending, meta, cfg) -> str:
    L = []
    L.append(BAR)
    L.append(" NSE SCANNER - TOP RECOMMENDATIONS")
    if meta.get("as_of_n"):
        ends = f"latest bar for {meta['as_of_n']} of {meta['U']} scanned stocks"
    else:
        ends = "latest bar in the data"
    L.append(f" Data as-of : {meta['date']} ({ends})        Generated: {meta['generated']} IST")
    emas = "/".join(str(p) for p in cfg.weekly.ema_set)
    L.append(f" Setup      : Daily MACD-histogram bullish divergence + weekly EMA({emas}) support zone")
    ill = meta.get("illiquid_pass") or []
    if meta.get("listed"):
        # Step 1 labels history with the thresholds in force at download time; Step 2 re-checks
        # with the current ones, so both counts are included.
        hist2 = (meta.get("skips") or {}).get("insufficient_history", 0)
        skipped = meta.get("skipped_insufficient", 0) + hist2
        L.append(f" Universe   : {meta['listed']} NSE equities listed | {meta['U'] - hist2} had enough "
                 f"history and were scanned")
        L.append(f"              ({skipped} skipped - under {cfg.data.min_rows_daily} trading days / "
                 f"{cfg.weekly.min_weekly_bars_for_zone} weekly candles of history) | "
                 f"{meta['L']} passed liquidity")
    else:
        L.append(f" Universe   : {meta['U']} EQ scanned | {meta['L']} passed liquidity")
    under = meta.get("under_min_score") or []
    extra = f" + {len(under)} under min_score (named in the summary)" if under else ""
    if cfg.liquidity.apply_as_filter:
        L.append(f" Flagged    : {meta['F'] + len(ill)} pass the setup (the spec's flag): {len(ranked)} ranked "
                 f"below{extra} + {len(ill)} that fail liquidity (listed at the end) | {meta['P']} pending")
    else:
        L.append(f" Flagged    : {meta['F']} pass the setup (the spec's flag): {len(ranked)} ranked below{extra} | "
                 f"{meta['P']} pending")
    if meta.get("week_note"):
        L.extend(textwrap.wrap(meta["week_note"], width=100, initial_indent=" NOTE       : ",
                               subsequent_indent="              "))
    if meta.get("partial"):
        L.append(f" NOTE       : PARTIAL run - {meta['U']} of ~{meta.get('universe_total', 'n/a')} symbols "
                 f"downloaded so far; this file refreshes when the full download finishes.")
    L.append(f" Settings   : {_settings_echo(cfg)}")
    L.append(f" Data source: yfinance (.NS, {cfg.data.price_adjustment}, "
             f"{'dividends unadjusted' if cfg.data.price_adjustment=='split_only' else 'total return'})")
    L.append(BAR)
    L.append("")
    L.extend(_section1(ranked, cfg, meta["date"]))
    L.append("")
    L.append(BAR)
    L.append("")
    L.extend(_section2(ranked, cfg, meta["date"]))
    L.append("")
    L.append(BAR)
    L.append("")
    pend = ", ".join(pending) if pending else "(none)"
    L.append(f" PENDING (the swing-low week's candle is not complete in the data yet; re-checked on the next "
             f"download): {pend}")
    L.append("")
    if cfg.liquidity.apply_as_filter:
        L.append(f" PASSES THE SETUP BUT FAILS LIQUIDITY - {len(ill)} (not ranked; the floor is Rs "
                 f"{cfg.liquidity.min_median_traded_value_inr / 1e7:g} cr/day traded and price >= Rs "
                 f"{cfg.liquidity.min_price:g}; shown: what each one fell short on; every spec field is in the "
                 f"APPENDIX)")
        row = []  # wrap at ~100 chars without splitting an entry
        for e in [_illiquid_reason(x, cfg, meta["date"]) for x in ill] or ["(none)"]:
            if row and len("   " + ", ".join(row + [e])) > 100:
                L.append("   " + ", ".join(row) + ",")
                row = []
            row.append(e)
        L.append("   " + ", ".join(row))
        L.append("")
    skips = meta.get("skips") or {}
    under = meta.get("under_min_score") or []
    if skips or under:
        L.append(" SCAN SUMMARY (why the other stocks were not selected)")
        hist2 = skips.get("insufficient_history", 0)
        L.append(f"   scanned {meta['U'] - hist2} | passed liquidity+history {meta['L']} | "
                 f"setups {meta['F'] + len(ill)} ({len(ranked)} ranked, {len(under)} under min_score, "
                 f"{len(ill)} fail liquidity) | pending {meta['P']}")
        if under:
            L.append(f"   under min_score (pass the setup and liquidity, not listed): {', '.join(under)}")
        label = {
            "illiquid": "below liquidity/price floor (not a setup, or its week is still forming)",
            "insufficient_history": (f"too little history (under {cfg.data.min_rows_daily} days / "
                                     f"{cfg.weekly.min_weekly_bars_for_zone} weeks)"),
            "no_divergence:criteria_not_met": "no valid bullish divergence",
            "no_divergence:recent_window_open": "newest dip's price window not closed yet",
            "no_divergence:fewer_than_two_troughs": "fewer than two troughs",
            "zone:zone_fail": ("swing-low week did not touch the weekly EMA zone"
                               if cfg.weekly.zone_test == "range_overlap"
                               else "swing-low week did not close inside the weekly EMA zone"),
        }
        for k, v in sorted(skips.items(), key=lambda x: -x[1]):
            L.append(f"     {v:>5}  {label.get(k, k)}")
        fails = meta.get("failed_symbols") or []
        if fails:
            shown = ", ".join(fails[:15]) + (" ..." if len(fails) > 15 else "")
            L.append(f"   fetch-failed ({len(fails)}): {shown}")
        L.append("")
    L.append(" NOTES")
    lb = cfg.rsi.lower_band
    L.append(f'  - "uncensored" = the dip stayed at/above RSI {lb:g} (healthier). "censored" = it dipped')
    L.append(f"    below {lb:g} (weaker) but the stock is STILL listed (the RSI check only labels, it")
    L.append("    never removes a stock).")
    L.append("  - Every number in this report is computed from the downloaded data. The latest bar is")
    who = f"{meta['as_of_n']} of {meta['U']} scanned stocks" if meta.get("as_of_n") else "the scanned stocks"
    L.append(f"    {meta['date']} for {who}; a listed stock whose data ends on another date is marked "
             f"\"(data to <date>)\".")
    L.append("    This is not investment advice; always verify each chart before acting.")
    if cfg.liquidity.apply_as_filter:
        L.append("")
        L.extend(_appendix(ill, cfg, meta["date"]))
    L.append(BAR)
    return "\n".join(L) + "\n"


def _appendix(ill, cfg, as_of) -> list:
    """Spec 4/5 fields for every setup that fails liquidity (they pass the spec; not ranked)."""
    e = cfg.weekly.ema_set
    lines = [f" APPENDIX - EVERY SPEC FIELD FOR THE {len(ill)} SETUPS THAT FAIL LIQUIDITY (not ranked)",
             f"   DIP = MACD-histogram trough date (MACD value); LOW = swing-low price @ its date; ZONE WK = start "
             f"of the weekly EMA-zone candle;",
             f"   RSI = the lowest RSI within {cfg.divergence.price_window_k} days of the recent dip (check vs "
             f"{cfg.rsi.lower_band:g})",
             "",
             f"   {'SYMBOL':<12} {'PREV DIP (MACD)':<22} {'RECENT DIP (MACD)':<22} {'PREV LOW @ DATE':<23} "
             f"{'RECENT LOW @ DATE':<23} {'ZONE WK':<10}  {' / '.join(f'EMA{p}' for p in e):<27} RSI (CHECK)"]
    if not ill:
        lines.append("   (none)")
    for x in ill:
        emas = " / ".join(_lvl(x["ema_vals"].get(p)) for p in e)
        prev_dip = f"{x['prev_date'].date().isoformat()} ({_h(x['h_prev'])})"
        rec_dip = f"{x['recent_date'].date().isoformat()} ({_h(x['h_recent'])})"
        prev_low = f"{_num(x['pl_prev'])} @ {x['swing_prev_date'].date().isoformat()}"
        rec_low = f"{_num(x['pl_recent'])} @ {x['swing_recent_date'].date().isoformat()}"
        lines.append(
            f"   {x['symbol']:<12} {prev_dip:<22} {rec_dip:<22} {prev_low:<23} {rec_low:<23} "
            f"{x['week_start'].date().isoformat():<10}  {emas:<27} "
            f"{_num(x['rsi_trough'])} ({x['rsi_check']}){_data_to(x, as_of)}"
        )
    return lines


def _flagged_dataframe(ranked, illiquid=()) -> pd.DataFrame:
    """Every spec flag: the ranked setups, then the ones that fail liquidity (ranked=False,
    no rank/score)."""
    rows = []
    for is_ranked, r in [(True, r) for r in ranked] + [(False, r) for r in illiquid]:
        z = (r.get("z") or {}) if is_ranked else {}
        rows.append({
            "ranked": is_ranked,
            "rank": r.get("rank") if is_ranked else None,
            "symbol": r["symbol"],
            "company": r["company"],
            "isin": r["isin"],
            "score": r.get("score") if is_ranked else None,
            "Trough_prev_date": r["prev_date"].date().isoformat(),
            "Trough_prev_H": r["h_prev"],
            "pl_prev": r["pl_prev"],
            "swing_prev_date": r["swing_prev_date"].date().isoformat(),
            "Trough_recent_date": r["recent_date"].date().isoformat(),
            "Trough_recent_H": r["h_recent"],
            "pl_recent": r["pl_recent"],
            "swing_recent_date": r["swing_recent_date"].date().isoformat(),
            "momentum_ok": r["momentum_ok"],
            "price_ok": r["price_ok"],
            "Zone_week_date": r["week_start"].date().isoformat(),
            "weekly_bucket_fri": r["W"].date().isoformat(),
            **{f"ema{p}": v for p, v in r["ema_vals"].items()},
            "band_lo": r["band_lo"],
            "band_hi": r["band_hi"],
            "week_low": r["week_low"],
            "week_high": r["week_high"],
            "week_close": r["week_close"],
            "zone_ok": r["zone_ok"],
            "RSI_trough_value": r["rsi_trough"],
            "RSI_check": r["rsi_check"],
            "liquidity_inr": r["liquidity"],
            "last_close": r["last_close"],
            "last_date": pd.Timestamp(r["last_date"]).date().isoformat(),
            "atr14": r["atr14"],
            "z_momentum": z.get("momentum"),
            "z_zone_confluence": z.get("zone_confluence"),
            "z_rsi_quality": z.get("rsi_quality"),
            "z_liquidity": z.get("liquidity"),
            "z_recency": z.get("recency"),
            "z_volume_expansion": z.get("volume_expansion"),
        })
    out = pd.DataFrame(rows)
    if len(out):
        out["rank"] = out["rank"].astype("Int64")  # whole numbers even with unranked (blank) rows
    return out


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
        _flagged_dataframe(ranked, meta.get("illiquid_pass") or []).to_csv(p_csv, index=False)
        paths["csv"] = p_csv

    return paths


def now_ist() -> str:
    # IST = UTC+5:30 (no OS tz dependency).
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d %H:%M")

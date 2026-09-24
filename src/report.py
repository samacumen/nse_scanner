"""Report writer (blueprint 8.7).

TRUTHFULNESS MANDATE: every printed value comes from the computed record.
Nothing hardcoded/placeholder. Unfetchable field -> 'n/a'.
Writes ONE top_recommended_for_<DATE>.txt per day, glance-first: AT A GLANCE + HOW TO READ,
Section 1 top-N table, Section 2 top-N in plain words, Section 3 every other ranked setup,
Section 4 setups waiting for their week to close, Section 5 setups that fail liquidity, then
the scan summary, the settings used and notes. Every spec-5 field of every flag is printed.
Overwritten on re-run; optional flagged_<DATE>.csv when [output] write_full_flagged_csv = true.
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


def _d(ts) -> str:
    return pd.Timestamp(ts).date().isoformat() if ts is not None else "n/a"


def _turnover(liq_inr) -> str:
    """Rs crore traded per day: whole numbers from 10, else 2 decimals (thinly traded stocks)."""
    if liq_inr is None or pd.isna(liq_inr):
        return "n/a"
    cr = liq_inr / 1e7
    if 0 < cr < 0.005:
        return "<0.01"
    return f"{cr:.0f}" if cr >= 10 else f"{cr:.2f}"


def _glance_head(mid_title: str, mid_w: int) -> list:
    return [
        f"   {'#':>4}  {'SYMBOL':<10}  {'COMPANY':<20}  {mid_title:<{mid_w}}  {'PREV DIP':<10}  "
        f"{'RECENT DIP':<10}  {'ZONE WK':<10}  {'RSI (CHECK)':<18}  {'Rs cr/d':>7}",
        f"   {'-' * 4}  {'-' * 10}  {'-' * 20}  {'-' * mid_w}  {'-' * 10}  {'-' * 10}  {'-' * 10}  "
        f"{'-' * 18}  {'-' * 7}",
    ]


def _glance_row(r, as_of: str, num: str, mid: str, mid_w: int) -> str:
    rsi = f"{_num(r['rsi_trough']):>5} {r['rsi_check']}"
    return (f"   {num:>4}  {r['symbol']:<10}  {(r['company'] or '')[:20]:<20}  {mid:<{mid_w}}  "
            f"{_d(r['prev_date'])}  {_d(r['recent_date'])}  {_d(r['week_start'])}  {rsi:<18}  "
            f"{_turnover(r['liquidity']):>7}{_data_to(r, as_of)}")


def _detail_row(r, cfg) -> str:
    """The spec-5 numbers behind a glance row: MACD at both dips, both price lows with their dates,
    the zone week's price range and the weekly EMAs."""
    e = cfg.weekly.ema_set
    emas = " / ".join(_lvl(r["ema_vals"].get(p)) for p in e)
    return (f"          MACD {_h(r['h_prev'])} -> {_h(r['h_recent'])} | LOW {_num(r['pl_prev'])} @ "
            f"{_d(r['swing_prev_date'])} -> {_num(r['pl_recent'])} @ {_d(r['swing_recent_date'])} | "
            f"WEEK {_lvl(r['week_low'])} to {_lvl(r['week_high'])} | EMA{'/'.join(str(p) for p in e)} {emas}")


def _section1(top, cfg, as_of="") -> list:
    lines = [f" SECTION 1 - TOP {len(top) or cfg.ranking.top_n} (ranked by SCORE)", ""]
    lines += _glance_head("SCORE", 6)
    lines += [_glance_row(r, as_of, str(r["rank"]), f"{_num(r['score']):>6}", 6) for r in top] or ["   (none)"]
    return lines


def _rows_section(rows, cfg, as_of, mid_title, mid_w, mid_fn, num_fn) -> list:
    """A glance line + an indented line of spec numbers per stock, with a gap every 5 stocks."""
    lines = _glance_head(mid_title, mid_w)
    if not rows:
        return lines + ["   (none)"]
    for i, r in enumerate(rows):
        if i and i % 5 == 0:
            lines.append("")
        lines.append(_glance_row(r, as_of, num_fn(r), mid_fn(r), mid_w))
        lines.append(_detail_row(r, cfg))
    return lines


def _settings_lines(cfg) -> list:
    d, liq = cfg.divergence, cfg.liquidity
    emas = "/".join(str(p) for p in cfg.weekly.ema_set)
    zone = "range overlap" if cfg.weekly.zone_test == "range_overlap" else "close in band"
    liq_txt = (f"liquidity >= Rs {liq.min_median_traded_value_inr / 1e7:g} cr/day and price >= Rs "
               f"{liq.min_price:g} ({liq.window}-day median)" if liq.apply_as_filter else "liquidity filter off")
    adj = "dividends unadjusted" if cfg.data.price_adjustment == "split_only" else "total return"
    return [
        " SETTINGS USED",
        f"   MACD {cfg.macd.fast}/{cfg.macd.slow}/{cfg.macd.signal} | {d.lookback_days}-day lookback | "
        f"trough pivot +-{d.trough_pivot_k} bars | price/RSI window +-{d.price_window_k} bars",
        f"   equal-low tolerance {d.tolerance_pct * 100:g}% on {d.price_field} | weekly EMA {emas}, zone = {zone} | "
        f"history >= {cfg.data.min_rows_daily} days and {cfg.weekly.min_weekly_bars_for_zone} weeks",
        f"   RSI {cfg.rsi.period} ({cfg.rsi.smoothing}), band {cfg.rsi.lower_band:g} | {liq_txt} | "
        f"top {cfg.ranking.top_n}",
        f"   data: yfinance (.NS), split-adjusted, {adj}",
    ]


def _price_dir_word(pl_recent, pl_prev):
    if pl_recent < pl_prev:
        return "a LOWER low"
    if pl_recent == pl_prev:
        return "an EQUAL low"
    return "an EQUAL low (within tolerance)"


def _section2(ranked, cfg, as_of="") -> list:
    lines = []
    lines.append(f" SECTION 2 - WHY THE TOP {len(ranked) or cfg.ranking.top_n} (plain words, with the numbers "
                 f"behind each check)")
    if not ranked:
        lines += ["", "   (none)"]
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
            f"     3) RSI health: the lowest RSI within {k} trading days of the MACD dip was {_num(r['rsi_trough'])} "
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
                f"     4) Liquidity: about Rs {_turnover(r['liquidity'])} cr traded per day, below "
                f"{' and '.join(below)} => below the liquidity/price floor (listed only because the "
                f"liquidity filter is off)."
            )
        else:
            lines.append(
                f"     4) Liquidity: about Rs {_turnover(r['liquidity'])} cr traded per day "
                f"(above the Rs {floor_cr:g} cr minimum) => tradeable."
            )
    return lines


def _shortfall(x, cfg) -> str:
    """What a setup below the liquidity floor falls short on: turnover (its value is in the
    Rs cr/d column) and/or price."""
    parts = []
    liq, px = x["liquidity"], x["last_close"]
    if not liq >= cfg.liquidity.min_median_traded_value_inr:  # NaN-safe: missing turnover fails too
        parts.append("turnover" if pd.notna(liq) else "turnover n/a")
    if not px >= cfg.liquidity.min_price:
        parts.append(f"price Rs {px:.2f}" if pd.notna(px) else "price n/a")
    return ", ".join(parts)


def build_report_text(ranked, pending, meta, cfg) -> str:
    top_n = cfg.ranking.top_n
    ill = (meta.get("illiquid_pass") or []) if cfg.liquidity.apply_as_filter else []
    as_of = meta["date"]
    emas = "/".join(str(p) for p in cfg.weekly.ema_set)
    k, lb = cfg.divergence.price_window_k, cfg.rsi.lower_band
    who = f"{meta['as_of_n']} of {meta['U']} scanned stocks" if meta.get("as_of_n") else "the scanned stocks"
    gap = ["", BAR, ""]
    L = [BAR, " NSE SCANNER - WEEKLY SETUPS",
         f" Data to   : {as_of} (latest bar for {who})",
         f" Generated : {meta['generated']} IST", BAR, ""]

    # ---- AT A GLANCE ----
    L.append(" AT A GLANCE")
    n_flags = len(ranked) + len(ill)
    L.append(f"   {n_flags} stock{'s pass' if n_flags != 1 else ' passes'} the setup (the spec's flag):")
    where = (f"#1-#{top_n} in Sections 1-2, #{top_n + 1}-#{len(ranked)} in Section 3"
             if len(ranked) > top_n else "all in Sections 1-2")
    kind = "tradeable and ranked" if cfg.liquidity.apply_as_filter else "ranked (liquidity filter off)"
    L.append(f"     {len(ranked)} {kind}: {where}")
    if cfg.liquidity.apply_as_filter:
        L.append(f"     {len(ill)} thinly traded (fail the liquidity floor): Section 5, not ranked")
    L.append(f"   {meta['P']} more {'wait' if meta['P'] != 1 else 'waits'} for their week's candle to close: Section 4")
    if meta.get("listed"):
        # Step 1 labels history with the thresholds in force at download time; Step 2 re-checks.
        hist2 = (meta.get("skips") or {}).get("insufficient_history", 0)
        L.append(f"   Universe: {meta['listed']} NSE equities listed | {meta['U'] - hist2} with enough history "
                 f"({meta.get('skipped_insufficient', 0) + hist2} with too little) | {meta['L']} pass liquidity")
    else:
        L.append(f"   Universe: {meta['U']} scanned | {meta['L']} pass liquidity")
    if meta.get("week_note"):
        L.extend(textwrap.wrap("NOTE: " + meta["week_note"], width=96, initial_indent="   ",
                               subsequent_indent="         "))
    if meta.get("partial"):
        L.append(f"   NOTE: PARTIAL run - {meta['U']} of ~{meta.get('universe_total', 'n/a')} symbols downloaded "
                 f"so far; this file refreshes when the full download finishes.")
    L.append("")

    # ---- HOW TO READ ----
    zone = "touches" if cfg.weekly.zone_test == "range_overlap" else "closes inside"
    L += [" HOW TO READ",
          f"   SETUP    the daily MACD histogram makes a HIGHER low while the price makes a LOWER (or equal)",
          f"            low, and the weekly candle of that price low {zone} the weekly EMA {emas} band",
          "   DIPS     PREV / RECENT DIP = the dates of the two MACD-histogram troughs compared (daily chart)",
          "   ZONE WK  first trading day of the week whose candle is tested against the EMA band (weekly chart)",
          f"   RSI      the lowest RSI within {k} trading days of the recent dip, and its check:",
          f"              uncensored = it stayed at/above {lb:g} (a healthier dip)",
          f"              censored   = it fell below {lb:g} (oversold); still listed - RSI never removes a stock",
          "   SCORE    strength versus the other ranked setups (0 = average, higher = stronger)",
          f"   2nd line ({'Sections 3 and 5' if cfg.liquidity.apply_as_filter else 'Section 3'}) the spec's numbers, "
          f"earlier -> recent: MACD at the two dips |",
          "            LOW = the two price lows @ their dates | WEEK = the zone week's price range |",
          f"            EMA{emas} = the weekly averages that form the band",
          f"   Rs cr/d  median turnover of the last {cfg.liquidity.window} trading days, in Rs crore per day",
          f"   (data to <date>) marks a stock whose data ends on another date than {as_of}"]

    # ---- SECTIONS ----
    L += gap + _section1(ranked[:top_n], cfg, as_of)
    L += gap + _section2(ranked[:top_n], cfg, as_of)
    rest = ranked[top_n:]
    L += gap + [f" SECTION 3 - OTHER TRADEABLE SETUPS "
                f"({f'#{top_n + 1}-#{len(ranked)}' if rest else 'none'})",
                "   Each stock: a summary line, then its numbers, earlier -> recent (see HOW TO READ).", ""]
    L += _rows_section(rest, cfg, as_of, "SCORE", 6, lambda r: f"{_num(r['score']):>6}", lambda r: str(r["rank"]))
    L += gap + [f" SECTION 4 - WAITING FOR THEIR WEEK'S CANDLE TO CLOSE ({meta['P']})",
                "   Their price low is in a week whose candle is not complete in the data yet (normally the",
                "   current week, until Friday's 15:30 IST close). The weekly check needs a finished candle,",
                "   so they are re-checked on the next download.", ""]
    L.append("   " + (", ".join(pending) if pending else "(none)"))
    if cfg.liquidity.apply_as_filter:
        liq = cfg.liquidity
        L += gap + [f" SECTION 5 - THINLY TRADED SETUPS ({len(ill)}, not ranked)",
                    f"   They pass the setup but fail the liquidity floor (Rs {liq.min_median_traded_value_inr / 1e7:g} "
                    f"cr/day traded and price >= Rs {liq.min_price:g}).",
                    "   SHORT OF = what each one falls short on. Same two lines per stock as Section 3.", ""]
        L += _rows_section(ill, cfg, as_of, "SHORT OF", 24, lambda r: _shortfall(r, cfg), lambda r: "")

    # ---- SUMMARY, SETTINGS, NOTES ----
    skips = meta.get("skips") or {}
    if skips:
        L += gap + [" SCAN SUMMARY (why the other stocks were not selected)",
                    f"   scanned {meta['U']} | passed liquidity+history {meta['L']} | "
                    f"setups {len(ranked) + len(ill)} ({len(ranked)} ranked, {len(ill)} fail liquidity) | "
                    f"waiting {meta['P']}"]
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
        for key, v in sorted(skips.items(), key=lambda x: -x[1]):
            L.append(f"     {v:>5}  {label.get(key, key)}")
        fails = meta.get("failed_symbols") or []
        if fails:
            shown = ", ".join(fails[:15]) + (" ..." if len(fails) > 15 else "")
            L.append(f"   fetch-failed ({len(fails)}): {shown}")
    L += gap + _settings_lines(cfg)
    L += ["", " NOTES",
          "   - Every number in this report is computed from the downloaded data. The latest bar is",
          f"     {as_of} for {who}.",
          "   - Not investment advice; always verify each chart before acting.",
          BAR]
    return "\n".join(L) + "\n"


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

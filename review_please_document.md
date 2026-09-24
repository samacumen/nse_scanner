# Review request (round 2): NSE Scanner - Rule Spec v1.2 conformance after the review fixes

## 0. What I am asking you to do
You reviewed this build once already (round 1) and raised six issues. They have been fixed, and the
user made four decisions (section 2). Please re-review **read-only** against **NSE Scanner Rule Spec
v1.2** (the authoritative spec) and the code itself. Flag anything that:
- (a) contradicts the spec text or one of the user's stated decisions,
- (b) is a logic bug or a wrong edge case (trough / pair selection / zone / closed bars / RSI / report),
- (c) is an unstated assumption that could be wrong, or
- (d) does more or less than the spec plus the decisions.

Be concrete: spec clause, file:line, and a failing example. If something is correct, say so plainly;
do not invent issues. **End with a verdict as a percentage** of how close the build is to exact
(e.g. "95% - corrections needed: ..." listing exactly what closes the gap, or "100% - matches").

Repo root: `/home/sam/hobby_projects/nse_scanner` (branch `feature/v1.2`; round 1 reviewed commit
`3f1521a`; the round-2 fixes are commit `18ee3a0` - `git show 18ee3a0` shows every change). Spec: `prompts/NSE Scanner Rule Spec v1.2.docx`.

## 1. The tool in one paragraph
For each NSE stock: on the **daily** chart compute the MACD histogram, find the **troughs** (local
pivots of the histogram below zero), take the **two most recent** troughs in the last 60 bars, and call
it a **bullish divergence** when the newer trough is a *higher low in momentum* while price made an
*equal-or-lower low*. If so, map the recent trough's swing-low to its **weekly** candle and test that
the candle's range touches the **weekly EMA 11/22/50 band**. Passing both = the spec's flag; each flagged
stock gets an **RSI** label (never a filter). Product layer on top: flagged stocks that also pass a
liquidity floor are **ranked** (top 10 first); flagged stocks that fail liquidity are **listed
separately with the reason, never ranked**.

## 2. Round-1 findings -> fixes, and the user's decisions
All six round-1 findings were first reproduced independently on the same data (numbers matched yours
exactly: 261 literal passes; guards removed 42 + 21; 131 illiquid; 102 reported).

| # | Round-1 finding | Decision / fix | Where |
|---|---|---|---|
| 1 | Recency (20 bars) + confirmation (3 rising bars) gates drop valid spec passes | **User: drop both (literal spec 2).** The pair is exactly the two most recent pivot troughs in the last 60 bars; divergence = momentum AND price only. Freshness only feeds ranking (`recency = 1 - bars_since/LOOKBACK_DAYS`, z-scored). Evidence: 20 of the 21 confirmation rejects already had H back above the trough (one wobble failed the rule until H > 0). | `src/divergence.py`, `src/config.py`, `advanced_config.txt`, `src/rank.py` |
| 2 | Liquidity/history gates run before the flag; spec passes hidden | **User: list them separately.** The spec flag is computed for every history-qualified stock; liquidity applies AFTER it. A spec pass below the floor returns `illiquid_pass` and is listed in "PASSES THE SETUP BUT FAILS LIQUIDITY" with what it fell short on (turnover and/or price); never ranked. **User: history gate ~4y -> 1 year / 50 weekly candles** (`min_rows_daily` 1000 -> 250, `min_weekly_bars_for_zone` 200 -> 50). `min_score` is blank by default (removes nothing). | `scripts/run_scanner.py::analyze_symbol`, `src/report.py` |
| 3 | Closed bars (spec 7.5) not enforced | **User: close by clock after Friday 15:30 IST; no holiday calendar, no one-week delay.** Daily: Step 1 drops the newest bar when the download ran before that bar's own 15:30 IST close. Weekly: the last W-FRI bucket is closed iff a later week has data OR the data was **downloaded** at/after its Friday 15:30 IST (see 5.5 for why download time, not scan time). A Friday holiday needs no calendar. | `src/store.py::drop_forming_bar / session_close_utc`, `scripts/fetch_data.py`, `src/zone.py::_closed` |
| 4 | PRICE_WINDOW_K > TROUGH_PIVOT_K could compare an older pair | Always `prev, recent = troughs[-2], troughs[-1]`; if recent's `[t-K, t+K]` window is not closed yet -> not evaluated (`recent_window_open`), never an older pair. | `src/divergence.py::detect_divergence` |
| 5 | Narrative said "That low fell inside the band" (false for BSE) | Now "That week's price range touched <SYM>'s weekly EMA band" (range_overlap) / "That week closed inside" (close_in_band). It was false for 39 of 102 stocks. | `src/report.py::_section2` |
| 6 | Narrative printed the trough date for the price low | Now prints the swing-low date (spec 1.4). It was wrong for 47 of 102 stocks. | `src/report.py::_section2` |

Found by me (not in round 1), also fixed:
- **N1 As-of overstated.** Yahoo had published 2026-09-23 for only 3 of 1,594 stocks when Step 1 ran;
  the header used the max date. Now: as-of = the date most scanned stocks' data ends on (ties -> newest),
  shown with the count; Step 1 warns when the newest day is only partly published.
- **N2 Live golden tests were time bombs.** BSE formed a new, lower momentum trough on 2026-09-21, so a
  live fetch no longer flags BSE (spec-correct). The BSE golden + truthfulness tests now read a frozen
  copy of BSE's stored data (`tests/fixtures/BSE_2026-09-22.parquet`); all tests are offline.
- **N3 Step 1 cache window 120 h -> 12 h** (a re-run within 5 days silently re-downloaded nothing).
- **N4** With `apply_as_filter = false` the liquidity line said "above the minimum => tradeable" for
  every stock; it now says "below the ... minimum" when true.

Then an independent internal reviewer checked the round-2 working tree (verdict GO; it agreed with the
download-time choice in 5.5). Its findings, all fixed except M2:
- **M1** Step 1's "re-run later" advice was a no-op inside the 12 h reuse window -> the warning now
  says to set `refresh_if_older_than_hours = 0` for one run. **L2** it also warns (and names them) when
  some stocks end EARLIER than the rest (a per-stock Yahoo lag).
- **M2 (open, user decision)** illiquid spec passes are listed as symbol + shortfall only, without
  their spec-5 fields - see 5.3(c).
- **L1** RSI band "30" was hard-coded in report text -> printed from config. **L3** header history
  counts now include Step 2's own history re-check. **L5** missing turnover prints "turnover n/a".
  **L6** wording when only the price floor fails. **L7** Step 1 re-derives a cached file's status with
  the current history thresholds. **L4** a research script crashed on the new `illiquid_pass` kind.
  Plus small items (config docstring, a hard-coded 2292, `parse_fetched_at("nan")`).

## 3. The spec-critical code (verbatim)

### 3.1 Indicators (spec 1.1 / 1.5) - `src/indicators.py` (unchanged since round 1)
```python
def ema(x, n): return x.ewm(span=n, adjust=False).mean()
macd_line = ema(close, 12) - ema(close, 26); signal = ema(macd_line, 9); H = macd_line - signal
# RSI(14), Wilder smoothing (deviation 5.1):
d = close.diff(); gain = d.clip(lower=0); loss = (-d).clip(lower=0)
ag = gain.ewm(alpha=1/14, adjust=False).mean(); al = loss.ewm(alpha=1/14, adjust=False).mean()
rsi = (100 - 100/(1 + ag/al.replace(0, NaN))).fillna(100.0)
```

### 3.2 Troughs (spec 1.3) - `src/divergence.py::pivot_troughs` (unchanged since round 1)
```python
for t in range(k, n - k):                  # full +-k window (k = TROUGH_PIVOT_K = 3)
    if not h[t] < 0: continue              # strictly below zero
    if any(h[j] < h[t] for j in range(t-k, t+k+1) if j != t): continue   # a strictly lower neighbour disqualifies
    if t == prev_idx + 1 and h[t] == prev_val:   # adjacent tie-run -> keep the earliest only
        prev_idx = t; continue
    out.append(t); prev_idx = t; prev_val = h[t]
# find_troughs keeps troughs whose DATE is in the last LOOKBACK_DAYS (60) bars: t >= n - 60
```

### 3.3 Pair + divergence (spec 1.4 / 2) - `src/divergence.py::detect_divergence`
```python
troughs = find_troughs(H, cfg)
if len(troughs) < 2:
    return Divergence(False, reason="fewer_than_two_troughs")

# spec 2: the two most recent troughs. If the recent one's swing-low window is not
# fully closed yet (only possible when PRICE_WINDOW_K > TROUGH_PIVOT_K), wait.
prev, recent = troughs[-2], troughs[-1]
if recent > n - 1 - k:
    return Divergence(False, reason="recent_window_open")

pl_prev, sd_prev = _price_low(df, prev, k, field)        # min(Low[t-K : t+K]), earliest bar on ties
pl_recent, sd_recent = _price_low(df, recent, k, field)

momentum_ok = bool(h[recent] > h[prev])
price_ok = bool(pl_recent <= pl_prev * (1.0 + dv.tolerance_pct))
is_true = momentum_ok and price_ok
```

### 3.4 Weekly zone + closed week (spec 3.1 / 3.2 / 7.5) - `src/zone.py`
```python
def _closed(W, buckets, last_date, fetched_at=None) -> bool:
    """W (labelled by its Friday) is closed iff a later week has data, OR the data was
    downloaded at/after W's Friday 15:30 IST close. With no recorded download time,
    fall back to 'W's Friday bar is in the data'."""
    if W != buckets[-1]:
        return True
    if fetched_at is None:
        return pd.Timestamp(last_date) >= W
    return fetched_at >= session_close_utc(W)

W = first W-FRI bucket label >= swing_low_date                      # the week containing the swing low
week_start = daily.index.to_series().resample("W-FRI").min().loc[W]  # Zone_week_date = first trading day
if not _closed(W, buckets, last_date, fetched_at): -> pending_week
band_lo, band_hi = min/max(EMA11, EMA22, EMA50 of weekly Close at W)
zone_ok = (Low_W <= band_hi) and (High_W >= band_lo)               # spec 3.2 verbatim
```

### 3.5 Closed daily bars (spec 7.5) - `src/store.py` + `scripts/fetch_data.py`
```python
IST = timezone(timedelta(hours=5, minutes=30)); NSE_CLOSE_IST = time(15, 30)
def session_close_utc(day): return datetime.combine(day.date(), NSE_CLOSE_IST, tzinfo=IST).astimezone(utc)
def drop_forming_bar(df, fetched_at):
    if fetched_at < session_close_utc(df.index[-1]):   # the newest bar had not closed at download time
        return df.iloc[:-1]
    return df
# fetch_data.py: t_fetch = now(UTC) BEFORE the download; raw = drop_forming_bar(raw, t_fetch);
# the SAME t_fetch is stored as the parquet's fetched_at (used by 3.4).
```

### 3.6 Pipeline order - `scripts/run_scanner.py::analyze_symbol`
```python
if rows < 250 or weekly_bars < 50: skip "insufficient_history"
liq_ok = passes_liquidity(df)             # 20-day median Close*Volume >= Rs 5 cr AND last Close >= Rs 20
div = detect_divergence(...)              # 3.3
if not div.is_true: skip ("illiquid" if not liq_ok else div.reason)
zone = weekly_zone(df, div.swing_low_date, cfg, fetched_at)   # 3.4
if pending: ("pending" if liq_ok else skip "illiquid")
if not zone_ok: skip ("illiquid" if not liq_ok else "zone_fail")
if not liq_ok: return "illiquid_pass"     # spec pass, listed with its reason, never ranked
RSI_trough = min(RSI[recent-K : recent+K]); RSI_check = "uncensored" if >= 30 else "censored"   # label only
-> "flagged" record (ranked)
```

### 3.7 Parameters in force (spec 6)
```
MACD 12/26/9   LOOKBACK_DAYS 60   TROUGH_PIVOT_K 3   PRICE_WINDOW_K 3   WEEKLY_EMA_SET 11,22,50
PRICE_FIELD Low   RSI_PERIOD 14 (Wilder, 5.1)   RSI_LOWER_BAND 30   TOLERANCE_PCT 0.01 (5.2)
zone test = range overlap (spec 3.2)   history >= 250 daily bars AND >= 50 weekly bars (5.3)
liquidity (ranking only, 5.3): 20-day median traded value >= Rs 5 cr and price >= Rs 20
no recency / confirmation / separation gates (removed)
```

### 3.8 Output (spec 5) - `output/top_recommended_for_<DATE>.txt`
Section 1 (ranked): SYMBOL, COMPANY, SCORE, RSI label, PREV DIP (= Trough_prev_date), RECENT DIP
(= Trough_recent_date), ZONE WK (= Zone_week_date), LIQ. Section 2 per stock: both trough dates + H
values, both swing-low prices + dates, zone week, the three weekly EMAs + band + the week's range, RSI
trough value + label, liquidity. Then PENDING, then "PASSES THE SETUP BUT FAILS LIQUIDITY" (symbol +
turnover and/or price), then the scan summary. Optional CSV (`write_full_flagged_csv = true`) carries
every spec-5 field for the ranked stocks.

## 4. Clause-by-clause map (spec -> code)
| Spec | Implementation | Status |
|---|---|---|
| 0 flag = (A) divergence in last 60 AND (B) zone; RSI tag attached | 3.3 + 3.4 + 3.6; illiquid spec passes still listed | matches (ranking is a product layer on top) |
| 1.1 MACD 12/26/9 on Close | 3.1 | matches |
| 1.2 negative zone H < 0 | 3.2 | matches |
| 1.3 pivot trough, earliest on tie, Trough_date = bar t | 3.2 | matches |
| 1.4 swing low = min(Low) over [t-K, t+K], date of that bar | 3.3 `_price_low` | matches |
| 1.5 RSI 14 / SMA(14) / band 30 | 3.1 | **Wilder, see 5.1** |
| 1.6 RSI trough over the same [t-K, t+K] | 3.6 | matches |
| 2 last 60; < 2 troughs stop; two most recent; momentum; price with TOL | 3.3 | matches (TOL value: 5.2) |
| 3.1 week containing the swing-low date; Zone_week_date = start of W | 3.4 | matches (start = first trading day) |
| 3.2 zone_ok = (Low_W <= band_hi) and (High_W >= band_lo) | 3.4 | matches |
| 4 RSI labels, never filters | 3.6 | matches |
| 5 output fields | 3.8 | matches |
| 6 parameters | 3.7 | matches (MIN_SEGMENT_LEN dropped, 5.4) |
| 7.1 Low; 7.3 60 = sessions; 7.4 RSI only on shortlisted | 3.3 / 3.6 | matches |
| 7.5 fully closed daily AND weekly bars | 3.4 + 3.5 | matches (see 5.5, 5.6) |

## 5. Deliberate choices beyond the literal text - please judge
**5.1 RSI = Wilder(14)** (spec 1.5 says SMA(14)). Trader-confirmed FINAL: the desk reads RSI on
TradingView, whose default is Wilder. Affects only the censored/uncensored label.

**5.2 TOLERANCE_PCT = 1%** (spec 6 table says 0.1%). Trader-confirmed FINAL: at 0.1% the "equal low /
double bottom" branch essentially never fires.

**5.3 Product layer.** (a) History gate: a stock needs >= 250 daily bars AND >= 50 weekly bars (user
decision, ~1 year). Note: this counts ALL weekly bars; at the swing-low week W (up to ~12 weeks before
the last bar) the EMA50 of the youngest eligible stocks rests on ~38-50 weekly closes. Is that
acceptable, or should the 50-bar minimum apply at W? (b) Liquidity decides only ranked vs listed; it
never hides a spec pass (an illiquid stock whose zone week is still pending is not listed, as it is not
a pass yet). (c) Open question (internal review M2): the user chose a COMPACT list (symbol + what it
fell short on) for the illiquid spec passes, so their spec-5 fields (trough dates/H, swing lows, zone
week, EMAs, RSI value/check) are not printed. Strictly, spec 4/5 attach those fields to every
shortlisted stock. Should the compact list carry them (e.g. RSI label + the three dates), or is the
compact list right for a product whose ranked list is the actionable output?

**5.4 MIN_SEGMENT_LEN dropped** (spec 6 lists it, but spec 1.2/1.3 no longer use segments).

**5.5 Weekly closure uses the DOWNLOAD time, not the scan's current time.** The user's rule is "close
the week by clock after Friday 15:30 IST". The clock used is the time the data was downloaded
(`fetched_at`). Reason: Step 2 may be re-run later without re-downloading (a supported workflow). With
the scan's clock, data downloaded on Thursday evening and re-scanned on Saturday would treat a Mon-Thu
candle as the finished week. With the download clock it stays pending until the next download. In the
normal flow (Step 1 then Step 2) both clocks give the same answer. Do you agree?

**5.6 Residual: vendor lag.** If Yahoo has not yet published the newest session when Step 1 runs after
the close, that day is missing (a week could then be closed on a Mon-Thu candle). Mitigation: Step 1
warns when the newest day is published for only some stocks, and the report's as-of shows how many
stocks end on the as-of date; Step 1 names stocks that end earlier than the rest. A possible
code-level guard (not implemented, for your judgement): treat a stock's last week as NOT closed when
another stock in the universe has a later bar inside that same week (proof the stock's data is
incomplete). A universal lag (no stock has the day) is not detectable without a calendar. Acceptable?

**5.7 Residual: the 12-hour reuse window (user-approved).** Step 1 reuses a stock's file if it was
downloaded within the last 12 hours (to resume an interrupted run). Edge: Step 1 run before the 15:30
IST close (today's forming candle correctly dropped) and again after the close within 12 hours reuses
the morning files, so today's finished candle is missing until the next download. An alternative rule
would be "reuse only if no NSE session has closed since the file was downloaded". Worth changing, or
fine for a weekend cadence?

## 6. Evidence
- **Tests: 32 pass, all offline** (`.venv/bin/python -m pytest -q`):
  - The frozen BSE golden (Trough_prev 2026-08-21 H -18.13 low 3223.00; Trough_recent 2026-09-02
    H -3.49 low 3131.50; Zone_week_date 2026-08-31; band [3178.3, 3520.1]; RSI 33.29 uncensored).
  - Truthfulness: every printed number equals the computed value.
  - Pivot-rule units plus the round-1 #4 pair tests.
  - Closed-bar tests:
    - forming bar at 15:29 vs 15:30 IST;
    - the Good Friday 2026-04-03 week closes at Fri 15:30 IST;
    - a Friday-morning partial week stays pending;
    - the fallback when no download time is recorded.
  - Report-prose tests:
    - swing-low date in the narrative;
    - no "fell inside";
    - RSI band read from config;
    - truthful liquidity line;
    - illiquid list with its reasons;
    - the as-of count.
- **Fresh data.** Step 1 ran 2026-09-24 18:20-19:18 IST, after the close:
  - 2,320 EQ symbols, 0 failures.
  - 1,961 have >= 1 year of history (1,594 under the old ~4y gate); 359 skipped.
  - Data as-of 2026-09-24 for 1,960 of 1,961 stocks (PARIN's last bar is 2026-09-23).
- **Report `output/top_recommended_for_2026-09-24.txt`:**
  - 153 flagged and ranked.
  - 4 pending (CELLO, FIEMIND, UBL, VOLTAS: the swing low is in the current, unfinished week).
  - 153 more pass the setup but fail liquidity (listed with the shortfall).
  - 17 flagged stocks are "censored", which proves RSI never filters.
  - 26 flagged stocks have < 1,000 daily bars and were admitted by the 1-year gate (e.g. BELRISE,
    ENRIN, KAYNES, CEIGALL).
  - BSE is correctly NOT flagged on this data: its two most recent troughs are now 2026-09-02 and
    2026-09-21, and the later one is a lower momentum low.
- **Independent end-to-end recompute** (from scratch; only the MACD/RSI/EMA formulas are shared with
  the build). For every stored stock it recomputes:
  - the history gate and the pivots;
  - the two most recent troughs, and momentum + price;
  - the swing-low week, and whether that week is closed (by download time);
  - the zone and liquidity.

  It then compares against the WRITTEN report:
  - the flagged, pending and illiquid sets, and the as-of line;
  - for every flagged stock: trough dates, H values, swing lows + dates, Zone_week_date, band, RSI
    trough + label, and the narrative's "low on <swing date>".

  Result: **2,302 assertions, 0 mismatches.** The same recompute on the pre-refresh data (as-of
  2026-09-22) matched 130 flagged / 131 illiquid, against 102 flagged under the round-1 rules.
- **Data note:** Yahoo's history for a few long-listed stocks starts late (e.g. KIRLPNU's history
  starts 2023-04-26, with a 2:1 split on 2026-08-18). They are judged on the history Yahoo provides.

## 7. Please pressure-test specifically
1. Is each round-1 finding fully fixed, with no regression (section 2)?
2. `detect_divergence`: is `troughs[-2], troughs[-1]` plus the `recent_window_open` wait an exact
   reading of spec 2 under spec 7.5, for any PRICE_WINDOW_K / TROUGH_PIVOT_K?
3. Closed bars: any boundary error in `drop_forming_bar` / `_closed` (exactly 15:30 IST; UTC vs IST;
   bar dated a previous day; Friday holiday; missing `fetched_at`)? Do you agree with 5.5 and 5.6?
4. Does the liquidity-after-flag order change which stocks pass the spec's flag test in any case?
5. Is every printed claim in the report true (numbers, dates, the zone sentence, the as-of line)?
6. Anything in the spec that the build still does less or more than (sections 0-7)?

Please return: confirmed-correct items, issues (severity, file:line, spec clause, failing example),
and the one-line percentage verdict.

# Review request (round 4): NSE Scanner - Rule Spec v1.2 conformance after the round-3 fixes

## 0. What I am asking you to do
Round 3 scored the build **98%** with four items (one medium, two low, one dormant). They are fixed
below (section 2a), with the user's decisions. Please re-review **read-only** against **NSE Scanner Rule Spec
v1.2** (the authoritative spec) and the code itself. Flag anything that:
- (a) contradicts the spec text or one of the user's stated decisions,
- (b) is a logic bug or a wrong edge case (trough / pair / zone / closed bars / vendor lag / RSI / report),
- (c) is an unstated assumption that could be wrong, or
- (d) does more or less than the spec plus the decisions.

Be concrete: spec clause, file:line, and a failing example. If something is correct, say so plainly;
do not invent issues. **End with a verdict as a percentage** (e.g. "98% - corrections needed: ...",
or "100% - matches v1.2 and the stated decisions").

Repo root: `/home/sam/hobby_projects/nse_scanner`, branch `feature/v1.2`. History: round 1 reviewed
`3f1521a`; round-2 fixes = `18ee3a0`; round-3 fixes = `193d51e` (your five round-2 gaps + internal-review
follow-ups) and `521449e` (H1, Yahoo filler rows); round-4 fixes = 78dfddb (`git show 78dfddb`).
Spec: `prompts/NSE Scanner Rule Spec v1.2.docx`.

## 1. The tool in one paragraph
For each NSE stock: on the **daily** chart compute the MACD histogram, find the **troughs** (local
pivots below zero), take the **two most recent** troughs in the last 60 bars, and call it a **bullish
divergence** when the newer trough is a *higher low in momentum* while price made an *equal-or-lower
low*. Map the recent trough's swing-low to its **weekly** candle and test that the candle's range
touches the **weekly EMA 11/22/50 band**. Passing both = the spec's **flag**. Every flag gets its full
spec-4/5 record (RSI label included, never a filter). Product layer: flags that pass a liquidity floor
are **ranked** (top 10 first); flags that fail it are **listed with the reason and every spec-5
field in an appendix, never ranked**.

## 2a. Round-3 findings -> fixes (this round; user decisions in brackets)
| # | Round-3 finding | Fix | Where |
|---|---|---|---|
| 1 | A MISSING `data/week_check.json` silently skipped the NSE part of the guard | **[Warn, judge by clock]** A missing file - or a stale one left by an interrupted Step 1 - now yields a report NOTE and a console line: "NSE session check was not run for this download: each stock's last week is judged by the download time and the other stocks only." Every complete Step 1 run writes the file, so this only concerns such data - including the current 2026-09-24 data, downloaded before the check existed, whose report now shows that NOTE. | `src/store.py::load_week_guard` |
| 2 | A filler row at the START of a file survived (no previous close to compare) | After the general rule, the leading run of flat zero-volume rows is stripped too, so the first row kept is a real session (90 files, e.g. 3PLAND 2020-09-24). An all-filler file becomes empty and Step 2 skips it as insufficient history. No current result changed. | `src/store.py::drop_filler_rows`, `scripts/run_scanner.py` |
| 3 | "within 3 days" was calendar-ambiguous | "the lowest RSI within 3 trading days of the MACD dip" (report Section 2, appendix legend, docs). | `src/report.py` |
| 4 | `min_score` could hide spec flags and their spec-5 fields (dormant) | **[Remove the setting]** Removed from `config.txt`, `src/config.py`, `src/rank.py`, the scanner and the report: every liquid flag is always ranked and printed with its fields. | as listed |

## 2b. Round-2 findings -> fixes (made in round 3; for reference)
| # | Round-2 finding | Fix | Where |
|---|---|---|---|
| 1 | Illiquid flags lacked RSI and the spec-5 fields; header called only the ranked ones "flagged" | **[Appendix table]** Every spec pass now gets the full record (RSI included) from the same code path; `analyze_symbol` returns `("illiquid_pass", record)`. Header (2026-09-24 data): "Flagged : 308 pass the setup (the spec's flag): 156 ranked below + 152 that fail liquidity \| 5 pending". An **APPENDIX** lists, per illiquid flag: prev/recent trough date + H, prev/recent swing-low price @ date, Zone_week_date, EMA11/22/50, RSI_trough_value + RSI_check. The optional CSV holds all flags with a `ranked` column. Illiquid flags are no longer counted as skips. | `scripts/run_scanner.py::analyze_symbol`, `src/report.py::_appendix / build_report_text / _flagged_dataframe` |
| 2 | Vendor lag could close an incomplete last week | **[Cohort check + NSE check; fallback = cohort check + warning]** The last week stays pending if (a) another stock already has a later bar inside that week (this stock's feed lags), or (b) NSE held a session in that week that no stock's data has yet. (b) is checked by Step 1 only when the week is over by the clock but no stock has its later weekdays: it asks NSE's daily bhavcopy archive per missing weekday (200 = session held; 404 asked on a later day = no session / holiday; anything else = unknown) and writes `data/week_check.json`. NSE unreachable -> cohort check + clock, with a warning in the Step 1 log and a NOTE in the report. | `src/zone.py::_closed`, `src/store.py::last_week_check / load_week_guard`, `src/universe.py::nse_session_held / session_from_status`, `scripts/fetch_data.py` |
| 3 | 12 h cache could hide a newly finished session | A file younger than 12 h is reused only if no NSE weekday 15:30 IST close fell after its `fetched_at` (no calendar: a holiday weekday just causes one extra download); no `fetched_at` -> re-download. | `src/store.py::session_closed_between`, `scripts/fetch_data.py` |
| 4 | "RSI at the low" was often not literally true | Now "the lowest RSI within K days of the MACD dip" (spec 1.6's window), and "RSI stayed at/above 30 around the dip". | `src/report.py::_section2` |
| 5 | Closing "every number ... as of <date>" overstated one stock | Closing note: "The latest bar is <date> for <n> of <U> scanned stocks; a listed stock whose data ends on another date is marked '(data to <date>)'". Markers on Section 1 rows, Section 2 headings, the compact illiquid list and appendix rows (e.g. PARIN). | `src/report.py` |

Kept by user decision (your round-2 note): the 50-weekly-bar history gate counts the WHOLE history, not
bars up to W (AHCL has 49 and STLNETWORK 48 at W today).

**Also fixed this round (found by the internal reviewer; it dates back to v1.1) - H1, Yahoo filler
rows [user: per-stock rule].** Yahoo adds a flat, zero-volume row on NSE holidays. On 2026-01-15, 05-01,
05-28, 06-26 and 09-14, NSE's bhavcopy returns 404 (no session), yet 1,250-1,954 stocks had such a
row (RELIANCE included). Yahoo adds the same rows on days a thin stock did not trade. They are not sessions
(spec 7.3: bars = trading sessions; TradingView shows no bar), yet they entered MACD/RSI, the pivot
windows, the 60-bar lookback and the 20-day liquidity median. Rule (`src/store.py::drop_filler_rows`):
drop rows with Volume == 0 and Open == High == Low == Close == the previous close. It runs in Step 1
before any adjustment, and when data is loaded, so data stored before the rule is read the same way.
Effect on the 2026-09-24 data:
- 308 flags (156 ranked + 152 in the appendix) and 5 pending, against 306 (153 + 153) and 4 before.
- Example: BSE's 09-21 trough is H -2.897 on real sessions, but was -4.237 with the 09-14 holiday
  row. On real sessions that is a new bullish divergence (09-02 -> 09-21, price 3131.50 -> 3085.10),
  pending until this week closes.

## 3. The spec-critical code (verbatim or faithful excerpts)

### 3.1 Troughs, pair, divergence (spec 1.3 / 1.4 / 2) - `src/divergence.py` (unchanged since round 2)
```python
troughs = [t for t in pivot_troughs(h, TROUGH_PIVOT_K) if t >= n - LOOKBACK_DAYS]   # full +-k window, earliest on tie
if len(troughs) < 2: return Divergence(False, reason="fewer_than_two_troughs")
prev, recent = troughs[-2], troughs[-1]                       # spec 2: the two most recent
if recent > n - 1 - k: return Divergence(False, reason="recent_window_open")   # never an older pair
pl_prev, sd_prev = min(Low[prev-K : prev+K]), date          # earliest bar on ties
pl_recent, sd_recent = min(Low[recent-K : recent+K]), date
momentum_ok = h[recent] > h[prev]; price_ok = pl_recent <= pl_prev * (1 + TOLERANCE_PCT)
is_true = momentum_ok and price_ok                            # nothing else gates the pair
```

### 3.2 Weekly zone + closed last week (spec 3.1 / 3.2 / 7.5) - `src/zone.py`
```python
def _closed(W, buckets, last_date, fetched_at=None, guard=None) -> bool:
    if W != buckets[-1]:
        return True                                   # a later week has data
    if guard:
        newest = guard.get("cohort_newest")           # newest last bar of ANY downloaded stock
        if newest is not None and pd.Timestamp(last_date) < newest <= W:
            return False                              # another stock has a later bar in W: this feed lags
        if guard.get("incomplete_week") is not None and guard["incomplete_week"] == W:
            return False                              # NSE held a session in W that no stock has yet
    if fetched_at is None:
        return pd.Timestamp(last_date) >= W           # fallback: W's Friday bar is in the data
    return fetched_at >= session_close_utc(W)         # downloaded after W's Friday 15:30 IST
# W = first W-FRI label >= swing-low date; Zone_week_date = first trading day of W
# zone_ok = (Low_W <= max(EMA11,22,50 at W)) and (High_W >= min(...))     # spec 3.2 verbatim
```

### 3.3 Step 1: closed daily bars, week check, cache - `src/store.py`, `src/universe.py`, `scripts/fetch_data.py`
```python
# daily (spec 7.5): drop the newest bar if the download ran before its own 15:30 IST close
if fetched_at < session_close_utc(df.index[-1]): df = df.iloc[:-1]      # same instant stored as fetched_at

# week check, after all downloads (newest = newest last bar of any stock):
week = newest's W-FRI label (its Friday)
if now >= session_close_utc(week) and newest < week:
    for d in weekdays in (newest, week]:
        held = nse_session_held(d, now)   # GET BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip
        # 200 -> True; 404 and today (IST) > d -> False; anything else / network error -> None
        True -> sessions_missing; None -> unknown
-> data/week_check.json {"week", "cohort_newest", "checked_at", "sessions_missing", "unknown"}

# cache: reuse a file < 12 h old only if no NSE weekday 15:30 IST close fell after its fetched_at
```

### 3.4 Pipeline - `scripts/run_scanner.py::analyze_symbol`
```python
if rows < 250 or weekly_bars < 50: skip "insufficient_history"
liq_ok = passes_liquidity(df)        # 20-day median Close*Volume >= Rs 5 cr AND last Close >= Rs 20
div = detect_divergence(...)         # 3.1
if not div.is_true: skip ("illiquid" if not liq_ok else div.reason)
zone = weekly_zone(df, div.swing_low_date, cfg, fetched_at, week_guard)   # 3.2
if pending: ("pending" if liq_ok else skip "illiquid")
if not zone_ok: skip ("illiquid" if not liq_ok else "zone_fail")
RSI_trough = min(RSI[recent-K : recent+K]); RSI_check = "uncensored" if >= 30 else "censored"
record = every spec-5 field + ranking inputs
return ("flagged" if liq_ok else "illiquid_pass"), record     # both are spec flags
```

### 3.4b Filler rows (spec 7.3) - `src/store.py`
```python
def drop_filler_rows(df):
    c = df["Close"]
    same = lambda a, b: np.isclose(a, b, rtol=1e-6, atol=0.0)  # float noise only; a real tick is far larger
    flat0 = ((df["Volume"] == 0) & same(df["Open"], c) & same(df["High"], c) & same(df["Low"], c))
    out = df[~(flat0 & same(c, c.shift(1)))]
    # leading flat zero-volume rows have no previous close to compare with: drop them too
    lead = ((out["Volume"] == 0) & same(out["Open"], out["Close"]) & same(out["High"], out["Close"])
            & same(out["Low"], out["Close"]))
    start = int(np.argmin(lead.to_numpy())) if not lead.all() else len(out)
    return out.iloc[start:]
# Step 1: raw -> drop_forming_bar -> validate_and_prepare (dedup/sort -> drop_filler_rows -> adjust -> ...)
# Step 2 / tests: load_parquet(...) also applies drop_filler_rows
```

### 3.5 Parameters in force (spec 6)
```
MACD 12/26/9   LOOKBACK_DAYS 60   TROUGH_PIVOT_K 3   PRICE_WINDOW_K 3   WEEKLY_EMA_SET 11,22,50
PRICE_FIELD Low   RSI_PERIOD 14 (Wilder, 5.1)   RSI_LOWER_BAND 30   TOLERANCE_PCT 0.01 (5.2)
zone test = range overlap   history >= 250 daily AND >= 50 weekly bars (whole history)
liquidity (ranking only): 20-day median traded value >= Rs 5 cr and price >= Rs 20
no recency / confirmation / separation gates; no score floor (min_score removed in round 4)
```

### 3.6 Output (spec 5) - `output/top_recommended_for_<DATE>.txt`
Header (flag counts, as-of with count, NSE-check NOTE if any) -> SECTION 1 ranked list (PREV DIP =
Trough_prev_date, RECENT DIP = Trough_recent_date, ZONE WK = Zone_week_date, RSI label) -> SECTION 2
per ranked stock (both troughs + H, both swing lows + dates, zone week + EMAs + band + week range,
lowest RSI in the window + label, liquidity) -> PENDING -> PASSES THE SETUP BUT FAILS LIQUIDITY
(symbol + shortfall) -> SCAN SUMMARY -> NOTES -> APPENDIX (every spec-5 field per illiquid flag).
Optional CSV: every flag, `ranked` True/False.

## 4. Clause-by-clause map (spec -> code)
| Spec | Implementation | Status |
|---|---|---|
| 0 flag = divergence (last 60) AND zone; RSI attached | 3.1 + 3.2 + 3.4; all flags reported (ranked or appendix) | matches |
| 1.1 MACD 12/26/9 on Close | `src/indicators.py` | matches |
| 1.2 / 1.3 pivot trough, H < 0, earliest on tie | 3.1 | matches |
| 1.4 swing low = min(Low) over [t-K, t+K] + its date | 3.1 | matches |
| 1.5 RSI 14 / SMA(14) / band 30 | `src/indicators.py` | **Wilder, 5.1** |
| 1.6 RSI trough over the same [t-K, t+K] | 3.4; worded as "lowest RSI within K days of the MACD dip" | matches |
| 2 last 60; < 2 stop; two most recent; momentum; price with TOL | 3.1 | matches (TOL value 5.2) |
| 3.1 week of the swing-low date; Zone_week_date = start of W | 3.2 | matches |
| 3.2 zone_ok range overlap | 3.2 | matches |
| 4 RSI labels every shortlisted stock, never filters | 3.4 (ranked AND illiquid flags) | matches |
| 5 output fields for the shortlist | 3.6 (Sections 1-2 for ranked; APPENDIX for illiquid; CSV for all) | matches |
| 6 parameters | 3.5 | matches (MIN_SEGMENT_LEN dropped, 5.4) |
| 7.1 Low; 7.3 60 = trading sessions; 7.4 RSI only on shortlisted | 3.1 / 3.4 / 3.4b (Yahoo filler rows dropped) | matches |
| 7.5 fully closed daily and weekly bars | 3.2 + 3.3 | matches (residual 5.6) |

## 5. Deliberate choices beyond the literal text - please judge
**5.1 RSI = Wilder(14)** (spec says SMA(14)) and **5.2 TOLERANCE_PCT = 1%** (spec table 0.1%):
trader-confirmed FINAL.

**5.3 Product layer:** history gate >= 250 daily AND >= 50 weekly bars over the whole history (user
decision; not applied at W). Liquidity decides only ranked vs appendix; it never hides a flag, and
there is no score floor (round 4). An illiquid stock whose week is still pending is not listed (not a
flag yet).

**5.4 MIN_SEGMENT_LEN dropped** (orphaned in spec 6; spec 1.2/1.3 no longer use segments).

**5.5 Weekly closure by DOWNLOAD time** (you agreed in round 2).

**5.6 Vendor lag - residual.** Detected: a lag for SOME stocks (cohort check) and a lag for EVERY
stock when NSE answers (bhavcopy check). Not detected: a lag for every stock while NSE is unreachable
or answers ambiguously (e.g. asked on the day itself before NSE publishes); then the week is closed by
the clock, and both the Step 1 log and the report NOTE say so. The same NOTE appears when the check
file is missing (data downloaded before the check existed; round 4). Also: a stock that genuinely did not
trade on the week's last session (e.g. no trades that day) stays pending until the next week's data
arrives - conservative by design. Acceptable?

**5.7 Cache rule:** holiday weekdays count as a session close (no calendar), costing at most one
extra download. Acceptable?

**5.8 Filler rule scope (user-approved per-stock rule).** It also drops:
- a thin stock's no-trade days (TradingView shows no bar for those either);
- Yahoo's empty placeholders on 2025-03-18. That was a real session (bhavcopy 200), but ~1,822
  stocks carry a flat zero-volume row with no real data;
- (round 4) the leading run of flat zero-volume rows at the start of a file, where there is no
  previous close to compare with.

On data stored before the rule, Step 2 cleans it at load time. The download-time labels catch up
on the next Step 1 run. Until then, 5 young stocks with 250-252 stored rows (245-248 real sessions)
are labelled "ok" by Step 1, but Step 2's own history gate skips them and the header counts them.
Acceptable?

## 6. Evidence
- **Tests: 40 pass, all offline** (`.venv/bin/python -m pytest -q`). Round 4 adds:
  - a file starting with no-trade rows (applying the rule twice changes nothing);
  - the missing check-file note;
  - every liquid flag ranked (no `min_score`);
  - the "trading days" wording.

  New in round 3:
  - the cohort and NSE guards: a stock with only Mon-Thu data, downloaded Friday 17:30 IST, is
    closed by the clock alone but pending with either guard, and closed for a Friday holiday;
  - `last_week_check`: NSE is not asked before Friday 15:30 IST, nor when the Friday bar exists;
    Good Friday gives no missing session; held -> missing; unknown -> unknown;
  - NSE status mapping (200 / 404 on a later day / 404 on the day itself / 503);
  - `load_week_guard` notes;
  - the cache session rule across a close, an evening, a weekend and a Friday night;
  - the APPENDIX carries every spec-5 field and the "(data to ...)" marker;
  - flag counts; the CSV holds every flag with `ranked`;
  - an illiquid flag gets its RSI (BSE: 33.34 uncensored);
  - the filler rule (holiday + no-trade rows dropped; the five NSE holidays absent from the BSE
    fixture). BSE golden on the fixture: same dates, lows, zone week and band; H -18.153 / -3.493 and
    RSI 33.34 (were -18.127 / -3.491 and 33.29 with the fillers).
- **Live NSE check through the real code path (2026-09-24 21:13 IST):**
  - Good Friday week (newest bar 2026-04-02): no missing session, so the week is complete.
  - Normal week with its Friday missing from the data (newest 2026-09-17): `sessions_missing =
    ["2026-09-18"]`, so the week stays pending.
  - The current week (newest 2026-09-24, before Friday's close): NSE not asked.
- **Report `output/top_recommended_for_2026-09-24.txt`** (data downloaded 2026-09-24 18:20-19:18 IST;
  1,960 of 1,961 stocks end on 2026-09-24; PARIN ends 2026-09-23 and is marked):
  - 308 flags = 156 ranked + 152 in the appendix.
  - 5 pending: BSE, FIEMIND, INDIAMART, UBL and VOLTAS.
  - 12 of the 152 illiquid flags are censored (e.g. AKG, RSI 28.57); 16 of the ranked are censored.
  - "Passed liquidity" is 922 (909 with the fillers: the 20-day median no longer counts the
    zero-volume 09-14 row).
  - Round 4: the same selections. The header now carries the NOTE that the NSE session check was not
    run for this download, because the data predates the check.
- **Independent end-to-end recompute.** From scratch (only the MACD/RSI/EMA formulas are shared), it
  checks against the written report:
  - the flagged, pending and illiquid sets;
  - the as-of line and the flag-count header;
  - every ranked stock's trough dates, H, swing lows + dates, Zone_week_date, band, RSI + label, and
    the narrative low date and RSI wording;
  - every APPENDIX row: dates, H, lows, zone week, EMAs, RSI + label, data-to marker.

  Result: **3,723 assertions, 0 mismatches**, including a check that the 5 young stocks above are
  skipped by Step 2.
- **Internal reviewer (a second, independent check):**
  - Round-3 changes: GO. It confirmed the counts reconcile against the real report, and that the cohort
    guard held back 0 setups when replaying the real holiday Fridays 2026-05-01 and 2026-06-26.
  - Its follow-ups are fixed in `193d51e`: `min_score` header counts, stale/corrupt week-check file,
    NSE probe day, PENDING markers, small-value decimals, CSV integer ranks.
  - H1 was fixed as above, and the reviewer re-checked the fix across all 2,320 stored files: GO.
    - Applying the rule twice changes nothing, and consecutive fillers all go.
    - No row remains on any of the five holidays; the only market-wide dates removed are those five
      plus 2025-03-18.
    - Zero-volume bars that have a real price range are kept.
    - Its nits are in: a 1e-6 float tolerance, and one "scanned" count throughout the report.
  - Round-4 delta check: GO.
    - All four fixes are correct and minimal.
    - The new leading-filler strip changes nothing when applied twice, across 2,320 real files and
      20,000 random sequences.
    - Its two Low follow-ups are fixed: an all-filler file is now counted as scanned (a history skip),
      and a stale check file gets the same NOTE as a missing one.

## 7. Please pressure-test specifically
0. Are all four round-3 items (section 2a) fully fixed, with no regression?
1. Are all five round-2 findings still fixed?
2. `_closed` + `last_week_check` + `session_from_status`: any case where an incomplete week is
   treated as closed (other than 5.6's stated residual), or a complete week stays pending forever?
3. Is the APPENDIX a complete and faithful spec-5 record for every illiquid flag?
4. Does anything now count or print a flag inconsistently (header, Section 1, appendix, summary, CSV)?
5. Is every printed claim true (RSI wording, as-of note, data-to markers, NSE NOTE)?
6. Anything the build still does less or more than spec sections 0-7 plus the decisions?

Please return: confirmed-correct items, issues (severity, file:line, spec clause, failing example),
and the one-line percentage verdict.

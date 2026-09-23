# NSE Stock Scanner - Implementation Blueprint (v1.4, build-ready)

> **Purpose.** Single source of truth a developer *or an AI coding agent* follows to build the
> scanner. Written **ELI5** (plain language, nothing assumed) and **unambiguous** (exact formulas,
> exact parameters, exact file names). It implements the rule spec in
> `prompts/NSE Scanner Rule Spec v1.1.docx` **exactly**, except for a small set of deviations that
> are each **documented with empirical evidence** (§4) and required to make the spec self-consistent
> and tradeable. Flagged items for final sign-off are in §12.
>
> **Now tracks `prompts/NSE Scanner Rule Spec v1.2.docx`** (trough logic + output dates) - see the
> `v1.4 -> v1.5` changelog below; the divergence rule in §8.2 is the v1.2 pivot definition.
>
> **Status:** v1.1 - revised after the expert-trader adversarial review (verdict: GO-WITH-CHANGES)
> **and** an empirical validation run. **No product code is written until the user greenlights.**

## Changelog v1.0 → v1.1 (what the expert review + validation changed)
- **Pinned ONE trough algorithm** using `scipy.signal.find_peaks` (true topographic prominence),
  replacing three inconsistent prototypes. Re-validated on BSE at full 6-year warm-up (§4, §8.2).
- **`MIN_SEGMENT_LEN` → 1** under prominence: `=2` *drops BSE's own Sep-02 swing low* (a 1-bar run)
  and breaks the spec's example. Prominence - not segment length - is now the noise filter (§4).
- **Real golden numbers** replace the earlier self-contradictory example (§8.7, §11).
- Added **causality guard** (≥K bars after the recent trough), **fixed confirmation off-by-one**,
  **min trough separation ≥ 7**, **recency guard**, **NSE-calendar-robust closed-week test**,
  **RSI 0/0 guard** (§8.1–§8.3).
- **Ranking fixes**: ATR-normalized momentum, clamped zone-confluence, small-cohort z-score guard,
  dropped the ambiguous `price_divergence`, added `recency` + `volume_expansion` (§8.6).
- **Defaults revised**: `tolerance_pct` 0.1% → **1%** (honors v1.1's double-bottom intent);
  liquidity floor → **₹5 cr/day** + **min price ₹20**; added optional index-membership pre-trim.
- **Feasibility proven** by a 50-symbol dry run (§4a): ~2% real fetch failure, ~90 min full run.
- **Note on one expert item overridden with evidence:** the review said `yfinance>=1.7` "doesn't
  exist" (true at its 2024 knowledge cutoff). Verified on this machine: **`yfinance 1.7.0`
  installs and works** in 2026. We **pin `yfinance==1.7.0`** (the validated version) + add a
  startup smoke-fetch (below).

## Changelog v1.1 → v1.2 (second expert pass - blockers B1/B2/B3 + should-fixes)
- **B1 - weekly-history gate:** the EMA-zone (a hard filter) needs a well-warmed weekly EMA50, so
  a stock must have **≥ `MIN_WEEKLY_BARS_FOR_ZONE` (200 ≈ 4y)** weekly bars (else skipped as
  `insufficient_history`). `min_rows_daily` raised 250 → **1000 (~4y)** (§6, §7, §8.3, §9).
- **B2 - unattended fetch trust:** (i) count/act on **`failed` only** (never conflate with
  `insufficient_history`) for the bhavcopy-failover threshold; (ii) **pin `yfinance==1.7.0`** +
  **startup smoke-fetch** (fail loud if Yahoo's shape changes); (iii) after each full run, **log the
  `failed` set and cross-check it against liquidity/index membership** so no liquid name is silently
  dropped. Empirically validated: **200 random-EQ sample → 0 hard failures** (§4a).
- **B3 - NaN-safe ranking:** z-scoring is **NaN-aware** (a missing metric imputes to the cohort mean
  → contributes 0; never nulls the whole column), and the ATR normalizer is finite-guarded (§8.6).
- **S1:** BSE prominence sweep 0.06–0.20 → stable (§4a). **S3:** closed-week claim corrected +
  scan-date test (§8.1). **S4:** `src/` must match the reference's *outputs on fixtures with these
  fixes applied*, not copy it bar-for-bar (§11). **S5:** dropped the no-op RSI "uncensored" bonus;
  `RSI_check` is a reported field + tie-break (§8.6).

## Changelog v1.2 → v1.3 (user request: one editable settings file, re-analyze without re-fetch)
- **All settings moved into one plain-text `config.txt`** (INI via stdlib `configparser`; PyYAML
  dependency dropped) - heavily commented, editable in any editor (§6).
- **Fetch/analyze split made explicit:** the ~2,000-stock download runs once; editing any analysis
  setting and re-running `scripts/run_scanner.py` **re-analyzes the already-sourced data with no
  re-fetch** (§6). Report header echoes the exact settings used.

## Changelog v1.4 -> v1.5 (upgrade to Rule Spec v1.2)
Rule Spec v1.2's Version Control table changed two things: **trough identification** and **MACD/EMA
dates on output**. Implemented exactly, with the user's greenlit choices:
- **Trough = local pivot (spec 1.3).** A bar `t` with `H(t) < 0` whose `H` is `<=` every `H` in
  `[t - TROUGH_PIVOT_K, t + TROUGH_PIVOT_K]` (t excluded); the earliest bar wins an adjacent tie.
  This finds **overlapping troughs** (several within one negative excursion), fixing the false
  negatives the v1.1 prominence rule (D1) missed. The prominence/strict methods and their knobs
  (`trough_detection`, `prominence_frac`, `min_segment_len`) are **removed** - the pivot rule is the
  single method. New knob **`TROUGH_PIVOT_K = 3`** (spec 6). Validated: BSE golden is unchanged (same
  7 troughs; prev 2026-08-21 / recent 2026-09-02), and the full cached universe moves 73 -> 92 flags.
- **"Two most recent troughs" (spec 2); separation guard dropped.** `min_trough_sep` and the non-spec
  `divergence_scope` option are **removed**; `prev` is simply the trough immediately before `recent`.
  The **confirmation** and **recency** guards are **kept** (user: "drop separation only") - they never
  loosen the spec, only avoid falling-knife / stale picks.
- **Output dates (spec 2 / 3.1 / 5).** Report + CSV now carry `Trough_prev_date`, `Trough_prev_H`,
  `Trough_recent_date`, `Trough_recent_H`, and **`Zone_week_date` = the START (first trading day) of
  weekly candle W** (shown instead of the W-FRI Friday label). Section 1 gains PREV DIP / RECENT DIP /
  ZONE WK columns for chart validation.
- **Unchanged (v1.2 did not touch):** MACD 12/26/9, `LOOKBACK_DAYS` 60, `PRICE_WINDOW_K` 3, weekly EMA
  11/22/50, RSI Wilder(14)/band 30 (D3 kept), `TOLERANCE_PCT` 1% (D5 kept), liquidity floor, ranking.

## Changelog v1.3 → v1.4 (user greenlight + build directives)
- **`config.txt` re-assessed for leanness (§6):** removed non-essential internal/single-implementation
  knobs (hardcoded in `src/`, listed under "Fixed in code"); kept every criteria + methodological
  lever. Any multi-value knob left in config **must have all its values implemented** (no dead options).
- **Output restructured to two readable sections (§8.7):** SECTION 1 = one numbered ranked list
  (1..N); SECTION 2 = ELI5 "why chosen + what it satisfied" per stock, with real numbers.
- **TRUTHFULNESS MANDATE (§8.7, §11):** the report is generated purely from computed data - nothing
  hardcoded/assumed; a golden test asserts printed values == computed values; unfetchable fields print
  `n/a`, never invented.
- **Build process:** two agents in parallel (implementer + expert reviewer) iterating to convergence,
  then a third greenlight agent that does not pass until implementer, reviewer, and requirements are
  fully aligned - implementing the blueprint **as written, no assumptions**.

---

## 0. How to read this
§1–§4 concept, deliverables, decisions, and the evidence-backed deviations. §4a validation results.
§5–§6 layout, environment, and the config (every knob). §7 **Script 1 (fetch)**. §8 **Script 2
(analyze)** with exact formulas. §9–§11 edge cases, build order, tests. §12 sign-off items.
`CODE_CAPS` = config parameters in §6.

## 1. What we are building (ELI5)
Scan **every regular NSE equity (~2,292 `EQ` symbols)** once a week; find stocks in a specific
"bottoming" setup; return the **10 best** with a full plain-English explanation of *why*.

Three questions per stock, in order:
1. **Momentum quietly turning up while price still falls?** On the **daily** chart the MACD
   *histogram* makes a **higher low** while price makes a **lower/equal low** - a **bullish
   divergence** (selling exhausting).
2. **Did that low happen at long-term support?** The **weekly** candle containing that price low
   must sit **inside the weekly EMA 11/22/50 band** (a support zone).
3. **Was the dip healthy?** Tag (never filter) with an **RSI check**: RSI at the low ≥ 30 →
   `uncensored`; below 30 → `censored`.

Pass #1 **and** #2 → **flagged ("Red Flag", flag=1)**. #3 adds a label. Then **rank** the flagged
set and present the **top 10** + the full flagged list.

Two programs: **Script 1** downloads/stores history for all symbols; **Script 2** reads it, runs
the rules, ranks, and writes **`top_recommended_for_<DATE>.txt`**.

## 2. The two deliverable scripts
| # | Command | Does | Output |
|---|---|---|---|
| 1 | `python scripts/fetch_data.py` | Download ~2,292 symbols' ~6y adjusted daily OHLCV; resumable, rate-limit-aware. | `data/daily/<SYMBOL>.parquet` + `data/manifest.csv` |
| 2 | `python scripts/run_scanner.py` | Read stored data, compute indicators, apply rules, rank, write report. | `output/top_recommended_for_<DATE>.txt` (ONE file/day; summary folded in) + optional `output/flagged_<DATE>.csv` (when `write_full_flagged_csv=true`) |

`<DATE>` = data as-of date = last trading day in the data (`YYYY-MM-DD`). Both scripts read
`config.txt` (§6), share `src/` (§5), and run identically on **Linux and Windows** (pure Python,
`pathlib`, UTF-8).

## 3. Locked decisions (confirmed with the user)
| Topic | Decision |
|---|---|
| **Data feed** | Free hybrid. Primary `yfinance` (`.NS`), **split/bonus-adjusted, dividends NOT adjusted**. Universe from NSE `EQUITY_L.csv`. Fallback: per-symbol direct Yahoo chart API (browser UA); optional bhavcopy for the tail. |
| **Universe + liquidity** | Scan full ~2,292 `EQ` (configurable); **liquidity floor** (20-day median traded value ≥ `LIQ_MIN_INR`, plus `MIN_PRICE`) drops untradeable microcaps from flagging and ranking. Optional index-membership pre-trim. |
| **Trough rule** | **Local-pivot** (Rule Spec v1.2 §1.3): `H<0` and `<=` all H in `[t-TROUGH_PIVOT_K, t+TROUGH_PIVOT_K]`, earliest on tie. Replaces the v1.1 prominence rule (see the `v1.4 -> v1.5` changelog); BSE golden unchanged. |
| **Top 10** | Rank flagged stocks by a composite; output **top 10** focus set **and** full flagged list. |
| **RSI smoothing** | **Wilder RMA(14)** (spec's "SMA(14)" = mis-copy from the TV dialog). |
| **Weekly zone anchor** | Week containing the **swing-low date**, **closed weeks only**; forming week → **wait** (pending). |
| **Trough confirmation** | Recent negative histogram move must have **turned back up** before flagging. |
| **Price adjustment** | **Split/bonus-adjusted, dividend-unadjusted** (matches TradingView). |
| **Cadence** | Weekly, run over the weekend after Friday close. |

Spec defaults kept: MACD 12/26/9, `LOOKBACK_DAYS`=60, `PRICE_WINDOW_K`=3, weekly EMA {11,22,50},
`PRICE_FIELD`=Low, `RSI_PERIOD`=14, `RSI_LOWER_BAND`=30. **Revised/added** knobs are marked in §6.

## 4. Evidence-backed deviations from the literal spec ⚠️
Each deviation was *proven necessary* by running the spec against its **own diagram example
(BSE Ltd)** end-to-end (`research/validate_pipeline.py`, yfinance split-adjusted, 6y).

> **SUPERSEDED for the trough rule (Rule Spec v1.2).** D1 and D2 below describe the v1.1 *prominence*
> trough algorithm. **v1.2 replaced it** with the explicit local-pivot definition (§1.3), which is
> what ships (see the `v1.4 -> v1.5` changelog and §8.2). `find_peaks` / `PROMINENCE_FRAC` /
> `MIN_SEGMENT_LEN` / `DIVERGENCE_SCOPE` / `MIN_TROUGH_SEP` are **removed**; the only trough knob is
> `TROUGH_PIVOT_K` (=3). D1/D2 are kept only as the historical rationale for why segment-length was
> the wrong noise knob. **D3-D5 still apply.**

**D1 - Trough detection = prominence, not "one trough per zero-crossed segment."** *(historical - superseded by the v1.2 pivot rule.)*
The literal rule (§1.2–1.3) needs a positive bar (zero-cross) between the two compared troughs.
BSE's divergence forms **within one 47-bar negative run**, so the literal rule finds too few troughs
and returns **DIVERGENCE=FALSE on the spec's own example**. Fix: a trough is a **local minimum of
`H` in negative territory** detected by `scipy.signal.find_peaks(-H, prominence=MIN_PROMINENCE,
distance=TROUGH_MIN_DISTANCE)`, where **`MIN_PROMINENCE = PROMINENCE_FRAC × max(|H|)` over the last
`LOOKBACK_DAYS`** (`PROMINENCE_FRAC` default **0.10**). `find_peaks` uses *true topographic
prominence*, so genuine sub-lows survive and tiny wiggles do not.

**D2 - `MIN_SEGMENT_LEN` = 1 (was 2).** *(historical - superseded by the v1.2 pivot rule.)* With
prominence as the noise filter, requiring a ≥2-bar negative run **drops BSE's actual swing low on
2026-09-02** (a sharp 1-bar dip, `H=-3.49`, whose low **3131.5** is the diagram's weekly `L3,131.5`).
Segment length is the wrong knob. The v1.2 pivot rule needs no segment-length knob at all (the ±K
window is the noise filter), so `MIN_SEGMENT_LEN` is removed.

**D3 - RSI = Wilder RMA(14)** (user-confirmed; spec text deemed a mis-copy).

**D4 - Guards the spec omits, required for tradeability & no-repaint:** confirmation, causality
(±K window fully known), recency, and a liquidity floor (§8). User-confirmed.

**D5 - `TOLERANCE_PCT` 0.1% → 1%.** v1.1's changelog widened the rule to "equal (with tolerance)
or lower lows" (double bottoms); at 0.1% the "equal" branch essentially never fires. Default 1%.
*(Flagged for user confirm, §12.)*

**Comparison scope (v1.2):** the **two most recent** pivot troughs are compared (spec 2), with **no
separation guard** - this reproduces the diagram (Aug-21 → Sep-02). *(v1.1 had a `DIVERGENCE_SCOPE`
switch and a ≥7-bar `MIN_TROUGH_SEP` guard; both removed in v1.2 so genuinely overlapping troughs
count.)*

### 4a. Validation evidence (already run - must stay green)
**BSE golden (production algo, 6y warm-up), reproduces the diagram exactly:**
- `Trough_prev` 2026-08-21 `H=-18.127` low 3223.00 → `Trough_recent` 2026-09-02 `H=-3.491`
  low **3131.50** (matches diagram `L3,131.5`); momentum ✓, price ✓, confirmed ✓.
- Weekly **W ending 2026-09-04** (diagram's green-arrow week): EMA11 3520.1 / EMA22 3498.0 /
  EMA50 3178.3 → band **[3178.3, 3520.1]**; week [L 3131.5, H 3474.0] → **zone_ok=True**.
- RSI-trough **33.29 → uncensored**; liquidity ₹1,599 cr/day.

**50-symbol dry run (20 large + 30 random EQ, 6y each):** the only hard failure was
`TATAMOTORS.NS` 404 - a **symbol rename** (→ track by ISIN, §7); 5 recent IPOs auto-skipped.

**200-symbol random-EQ tail sample (no large-cap padding - the real unattended test):**
**0 hard fetch failures** of 176 fetched (24 young stocks correctly `insufficient_history`) →
**REAL failure ≈ 0%**; **~2.3 s/symbol → ~88 min** full run; **liquidity floor removed ~48%**
(91 liquid of 176); **liquid flag rate ~8.8%** → a healthy funnel (~90 flagged liquid names →
ranked → top 10); 4/176 suspicious single-day jumps (adjustment sound). This clears the "tail
under-sampled" concern: yfinance `.NS` EQ coverage is reliable for an unattended weekly job.

**Prominence sensitivity sweep (BSE, `prominence_frac` 0.06→0.20):** BSE flags with the correct
Sep-02 low **at every setting** - Sep-02's topographic prominence (~11) sits far above even the
0.20 threshold (6.26). The `0.10` default is comfortably mid-range, not knife-edge.

---

## 5. Project layout & environment
```
nse_scanner/
├─ config.txt    requirements.txt   .venv/          # config.txt = the user-editable settings (§6)
├─ prompts/            # original spec (.docx), read-only
├─ inputs/             # this blueprint
├─ research/           # validation harness (validate_pipeline.py = pinned reference; others superseded)
├─ data/  universe/EQUITY_L.csv  daily/<SYMBOL>.parquet  manifest.csv
├─ output/ top_recommended_for_<DATE>.txt   (+ optional flagged_<DATE>.csv)
├─ src/    config.py universe.py fetch.py store.py indicators.py divergence.py
│          zone.py liquidity.py rank.py report.py
└─ scripts/ fetch_data.py   run_scanner.py       # the two deliverables (thin entry points)
```
**Env:** Python ≥3.10; `python -m venv .venv` then install `requirements.txt`:
`pandas>=2.2, numpy>=1.26, scipy>=1.11, yfinance==1.7.0, pyarrow>=15, requests>=2.31`.
(Settings use stdlib `configparser` - **no YAML dependency**.)
(All validated on this machine: pandas 2.3.3, numpy 2.2.6, scipy 1.15.3, yfinance 1.7.0.)
**yfinance is exact-pinned** (a floating minor can break Yahoo parsing mid-schedule); Script 1 does a
**startup smoke-fetch** (one known symbol) and aborts loudly if the API shape changed (§7).
No OS-specific calls; `pathlib` paths. **Scheduling (optional, README):** Linux `cron` Saturday;
Windows Task Scheduler weekly calling `.venv\Scripts\python.exe`.

## 6. Configuration - plain-text settings the user edits (`config.txt` + `advanced_config.txt`)
**Settings are split across two INI files (v1.5)** parsed by stdlib `configparser` (no YAML): the
everyday **`config.txt`** (universe scope, liquidity floor, `top_n`, `min_score`, CSV toggle,
`history_years`, `price_adjustment`) and the rarely-changed **`advanced_config.txt`** (the method
knobs: MACD, divergence internals, RSI, weekly-zone, ranking weights, fetch mechanics). `config.py`
holds a built-in default for **every** parameter and reads `advanced_config.txt` first then
`config.txt` (so the everyday file wins on any shared key); a **missing key or a missing/deleted
`advanced_config.txt` falls back to the coded default**. This keeps the everyday file short while
every spec §6 parameter stays fully configurable. Blank value = "unset/default"; lists are
comma-separated.

> **Re-analyze without re-downloading (user's explicit requirement).** The pipeline is split so the
> **~2,000-stock download happens once** (Script 1 → `data/`), and **tuning is instant**: edit any
> `[macd]/[divergence]/[weekly]/[rsi]/[liquidity]/[ranking]/[output]` setting and just re-run
> **`python scripts/run_scanner.py`** - it re-analyzes the **already-sourced** data and rewrites the
> report, **no re-fetch**. Only changing `[universe]` or `[data]` requires re-running
> `scripts/fetch_data.py` first. Each report header echoes the exact settings used (reproducibility).

**Re-assessed for leanness (user request):** `config.txt` holds **only settings a user would
realistically change to alter results**. Every knob below with multiple listed values **must have all
those values implemented** (truthful config - no dead options). Pure internal mechanics, fixed
NSE/methodology constants, and single-implementation "toggles" are **hardcoded in `src/`** and listed
under "Fixed in code" after the file.

```ini
# ===== NSE SCANNER SETTINGS - edit, save, re-run. =====
# Change anything BELOW [data] (i.e. [macd]..[output]) -> just re-run:  python scripts/run_scanner.py
#   (re-analyzes the ALREADY-DOWNLOADED ~2000 stocks; NO re-fetch)
# Change [universe] or [data] -> re-download first:                     python scripts/fetch_data.py

[universe]
series = EQ                      # comma-separated, e.g. EQ,BE
include_sme = false
index_filter =                  # blank = all EQ; or NIFTY500 / NIFTY500+SMALLCAP250 (faster, cleaner)
max_symbols =                   # blank = all; small integer to test on a subset
symbols_override =              # comma-separated to scan ONLY these (testing)

[data]
history_years = 6
price_adjustment = split_only   # split_only (matches TradingView) | total_return (incl. dividends)
request_throttle_sec = 0.5      # raise if Yahoo rate-limits you
min_rows_daily = 1000           # ~4y min history; else skipped (weekly EMA50 needs depth)
refresh_if_older_than_hours = 120  # reuse cached files newer than this (resume); 0 = always refetch

[macd]
fast = 12
slow = 26
signal = 9

[divergence]
lookback_days = 60
trough_pivot_k = 3              # spec 1.3 pivot window (TROUGH_PIVOT_K)
price_window_k = 3
tolerance_pct = 0.01            # 1% "equal low" band
price_field = Low               # Low | Close
require_confirmation = true
confirm_bars = 3
recency_bars = 20

[weekly]
ema_set = 11,22,50
zone_test = range_overlap       # range_overlap (wick touch) | close_in_band (stricter)
min_weekly_bars_for_zone = 200  # ~4y; the EMA50 zone is a hard filter and needs a warmed series

[rsi]
period = 14
smoothing = wilder              # wilder | sma
lower_band = 30

[liquidity]
apply_as_filter = true
window = 20
min_median_traded_value_inr = 50000000   # ₹5 cr/day
min_price = 20                            # ignore sub-₹20 names

[ranking]
top_n = 10
weight_momentum = 0.30
weight_zone_confluence = 0.20
weight_rsi_quality = 0.15
weight_liquidity = 0.15
weight_recency = 0.10
weight_volume_expansion = 0.10
min_score =                     # blank = no floor (never pad the list with weak names)

[output]
dir = output
write_full_flagged_csv = true
```

**Fixed in code (removed from `config.txt` - not results-affecting knobs a user would tune).** Each
is a `src/` constant; listed here so the choice is auditable (per the user's "be sure" rule - remove
only what's clearly non-essential): NSE `EQUITY_L.csv` URL; data-source strategy (yfinance primary →
Yahoo chart-API fallback - the only implemented sources); full weekly refetch (incremental is future
work); fetch resilience (batch size, retries, backoff); cache dir `data/daily`; the bhavcopy-failover
log threshold; weekly `resample_rule` = `W-FRI` (NSE week); zone `anchor` = swing-low week (the one
designed anchoring); ranking `tie_break` (liquidity) and `small_cohort_threshold` (=3); and the fixed report
filename pattern `top_recommended_for_<DATE>.txt`. *If the reviewer/greenlight judges any of these
user-essential, promote it back to `config.txt`.*

## 7. SCRIPT 1 - data fetcher (`scripts/fetch_data.py`)
Produce `data/daily/<SYMBOL>.parquet` (split-adjusted daily OHLCV, ~6y) + `data/manifest.csv`.
**Full weekly refetch** (not incremental) so the adjusted series is always internally consistent
(new splits retroactively re-scale history). ~90 min for the full universe (measured).

1. **Load config**; ensure dirs exist; **startup smoke-fetch** (one known symbol, e.g. `RELIANCE.NS`)
   - abort loudly if it returns empty or an unexpected shape (guards against yfinance/Yahoo drift).
2. **Universe** (`universe.py`): download `EQUITY_L.csv` with a **browser User-Agent**; if it returns
   non-CSV, **prime an NSE session** (GET `https://www.nseindia.com` first) then retry. **Strip the
   CSV's leading-space headers** (`' SERIES'` etc.). Keep `SERIES ∈ series`; build `(symbol, isin)`.
   Optional `index_filter` pre-trim. **Track identity by ISIN** and **diff against last week's
   snapshot** to detect adds/renames/drops (the `TATAMOTORS.NS`→404 case in §4a is a rename).
3. **Fetch loop** (`fetch.py`), resumable: skip fresh files (`skip_if_fetched_within_hours`).
   Primary `yfinance.download(f"{sym}.NS", period=f"{history_years}y", interval="1d",
   auto_adjust=False, actions=True, progress=False, threads=False)` → use **raw OHLC** (Yahoo
   split-adjusts these); keep `Adj Close`/`Dividends`/`Stock Splits` for audit; flatten MultiIndex.
   On empty/error → retry with backoff → **fallback** to direct Yahoo chart API
   (`range={years}y&interval=1d&events=splits`, browser UA). **Throttle** `request_throttle_sec`.
   **One bad symbol never aborts the run** (catch, log, continue).
4. **Validate & store** (`store.py`): require `≥ min_rows_daily` (1000) daily rows *and*
   `≥ min_weekly_bars_for_zone` (200) weekly bars, else `insufficient_history` - the weekly EMA50
   zone is a hard filter and needs the depth (B1). Sanity: increasing unique dates, positive prices, `High≥Low`;
   flag (don't crash on) unexplained single-day moves > 50%. Write parquet (Appendix A).
5. **`manifest.csv`**: `symbol,isin,ticker,source,rows,first_date,last_date,status,fetched_at`,
   `status ∈ {ok, insufficient_history, failed}`.
6. **Summary**: counts by status (`ok`/`insufficient_history`/`failed` kept **separate**), time,
   failures. The bhavcopy-failover threshold is computed on **`failed` only** (never
   `insufficient_history`/IPOs). After each full run, **write the `failed` set to the log and
   cross-check it against last-known liquidity/index membership** so no *liquid* name is silently
   dropped (a failed fetch on a would-be flag is an invisible miss). Validation measured **~0% real
   failures** on a 200-symbol random-EQ sample, so yfinance suffices today.

**Acceptance:** on `symbols_override=["BSE","RELIANCE","TCS"]` → 3 valid parquet, all `ok`, ~6y each.

## 8. SCRIPT 2 - analyzer (`scripts/run_scanner.py`)
Per symbol (skip `status≠ok`), then rank across all flagged, then write the report.
**Golden rule:** compute all indicators on the **full warmed** series, then slice the last
`LOOKBACK_DAYS` for trough selection - never on a truncated slice.

### 8.1 Indicators (`indicators.py`)
```
def ema(x,n): return x.ewm(span=n, adjust=False).mean()
macd_line = ema(close,12) - ema(close,26); signal = ema(macd_line,9); H = macd_line - signal
# Wilder RSI(14):
d=close.diff(); gain=d.clip(lower=0); loss=(-d).clip(lower=0)
ag=gain.ewm(alpha=1/14,adjust=False).mean(); al=loss.ewm(alpha=1/14,adjust=False).mean()
rsi = (100 - 100/(1 + ag/al.replace(0, NaN))).fillna(100.0)     # 0/0 flat → 100 (guard)
# ATR(14) for ranking:  tr=max(H-L,|H-Cprev|,|L-Cprev|); atr=tr.ewm(alpha=1/14,adjust=False).mean()
```
**Weekly** (resample the *adjusted daily* series):
```
wk = daily.resample("W-FRI").agg(Open=("Open","first"),High=("High","max"),
      Low=("Low","min"),Close=("Close","last"),Volume=("Volume","sum")).dropna(subset=["Close"])
EMA11/22/50 = ema(wk.Close, {11,22,50})
```
**Closed-week rule (no look-ahead):** a weekly bucket `W` (Friday label) is **closed** iff a later
weekly bucket already has daily data, **or** the as-of/scan date is on/after that week's Friday
label. Only the most-recent bucket can be "forming"; a swing low there defers to next week
(conservative - never a false flag). **Residual (low severity, not fully solved):** if a week's
Friday is a holiday and the scan runs that weekend, that just-ended week may be deferred one extra
week - a fully exact test needs the NSE trading calendar (a post-launch nicety). Acceptable for a
weekly cadence.

### 8.2 Divergence (`divergence.py`) - Rule Spec v1.2 §1.3-2
```
# Trough = local pivot in negative territory (spec 1.3); Kp = TROUGH_PIVOT_K (=3):
troughs = [t for t in range(Kp, n-Kp)                 # full +-Kp window (no look-ahead)
           if H[t] < 0 and H[t] <= H[j] for every j in [t-Kp, t+Kp], j != t]
#   adjacent bars tying for the minimum collapse to the earliest
troughs = [t for t in troughs if date(t) in last LOOKBACK_DAYS sessions]
if len(troughs) < 2: return flag0
# recent = latest trough with a fully-known swing window (t <= n-1-K) AND within RECENCY_BARS of the last bar
# prev   = the trough IMMEDIATELY BEFORE recent (spec 2: "the two most recent troughs")
if recent is None or prev is None: return flag0
PriceLow(t)      = min(Low over [t-K, t+K])           # K = PRICE_WINDOW_K; clamp to bounds
swing_low_date(t)= date of that min-Low bar (tie → earliest)
momentum = H[recent] > H[prev]
price_ok = PriceLow(recent) <= PriceLow(prev) * (1 + TOLERANCE_PCT)
# confirmation (require_confirmation): rising run from `recent` (incl. recent→next bar) ≥ CONFIRM_BARS,
#   OR H crosses > 0 after `recent`.
divergence = momentum and price_ok and confirmed
```
The two most recent pivot troughs are compared; there is no separation guard (v1.2). `recent` still
needs `TROUGH_PIVOT_K` closed bars after it (inherent to a pivot), so there is no look-ahead.

### 8.3 Weekly EMA zone (`zone.py`) - only if divergence
**Precondition (B1):** the weekly series must have `≥ min_weekly_bars_for_zone` (200) bars, else the
symbol was already skipped as `insufficient_history` at fetch - never compute an under-warmed EMA50
zone (it would corrupt this hard filter).
`swing = swing_low_date(recent)`; `W` = the `W-FRI` bucket containing `swing`.
If `W` not closed (§8.1) → **pending_week** (do not flag; list in the pending section §8.7).
`band_lo/hi = min/max(EMA11,EMA22,EMA50 at W)`; `zone_ok = (W.Low ≤ band_hi) and (W.High ≥ band_lo)`.
`zone_ok=True` → **flag=1**, else flag=0.

### 8.4 RSI tag (`indicators`/pipeline) - shortlisted only; never filters
`RSI_trough_value = min(RSI over [recent-K, recent+K])`;
`RSI_check = "uncensored" if ≥ RSI_LOWER_BAND(30) else "censored"`.

### 8.5 Liquidity (`liquidity.py`)
`liquidity = median(Close×Volume over last liquidity.window days)`. Exclude from flagging/ranking
if `apply_as_filter` and (`liquidity < min_median_traded_value_inr` **or** `last Close < min_price`).
`liquidity` also feeds ranking.

### 8.6 Ranking → top 10 (`rank.py`)
For each flagged stock (five→six metrics, higher = better):
| Metric | Raw |
|---|---|
| `momentum` | `(H[recent] − H[prev]) / ATR14`  *(ATR-normalized; not ÷|H_prev|)* |
| `zone_confluence` | `0.5·clamp(1 − (band_hi−band_lo)/Close_W, −1,1) + 0.5·clamp(1 − |Close_W − band_mid| / ((band_hi−band_lo)/2 + ε), −1,1)`, `band_mid=(band_lo+band_hi)/2` |
| `rsi_quality` | `RSI_trough_value` (higher = healthier dip). *(`RSI_check` is reported and used as a tie-break; no numeric bonus - a small bonus vanishes after z-scoring - S5)* |
| `liquidity` | `log10(liquidity)` |
| `recency` | `1 − bars_since(recent)/RECENCY_BARS` |
| `volume_expansion` | `Volume[recent] / median(Volume over last 20)` |
`score = Σ weightᵢ · zscore(metricᵢ)`. **NaN-safe (B3):** z-scoring ignores NaNs when computing
mean/std, and any NaN metric imputes to the cohort mean (contributes 0) - one bad metric can never
null the whole column/top-10; the ATR denominator of `momentum` is finite-guarded (§8.1).
**Small-cohort guard:** if `n_flagged < small_cohort_threshold` or a metric's std==0, skip z-scoring
that metric (contribute 0) and fall back to sorting by `momentum` then `liquidity`. Sort desc;
**top 10** = focus, **all** flagged listed. `tie_break` = liquidity (then `uncensored` before
`censored`). If `min_score` set, drop below it (never pad to 10). If >10 flag, highlight 10, list rest.

### 8.7 Output - `output/top_recommended_for_<DATE>.txt` (UTF-8, human-readable)
**TRUTHFULNESS MANDATE (hard requirement).** Every value printed is **computed from the actually
sourced data at run time - nothing hardcoded, sampled, placeholdered, or assumed.** The block below is
a **format template**; its numbers are illustrative (the BSE golden) and MUST be produced by the code,
never copied in. A golden test asserts the printed values equal the computed values (§11). If a field
can't be computed, print `n/a` - never invent it. Every listed stock must genuinely pass §8.2 + §8.3.

**Two sections (per user requirement):**
- **SECTION 1 - THE LIST:** one continuous numbered ranking (1, 2, 3, … `top_n`, then the remaining
  flagged names), compact columns.
- **SECTION 2 - WHY EACH WAS CHOSEN (ELI5):** for every listed stock, plain-English what-it-satisfied
  (the daily divergence, the weekly support zone, the RSI health tag), with the concrete numbers.

```
=====================================================================
 NSE SCANNER - TOP RECOMMENDATIONS
 Data as-of : <DATE> (last trading day)        Generated: <timestamp> IST
 Setup      : Daily MACD-histogram bullish divergence + weekly EMA(11/22/50) support zone
 Universe   : <U> EQ scanned | <L> passed liquidity | <F> flagged | <P> pending week-close
 Settings   : <echo the exact config values actually used this run>
 Data source: yfinance (.NS, split-adjusted, dividends unadjusted)
=====================================================================
 SECTION 1 - RANKED LIST   (#1..#<top_n> are the focus picks; the rest are the full flagged list)
   #   SYMBOL       COMPANY                    SCORE   RSI          LIQ ₹cr/d   ZONE WEEK
   1   BSE          BSE Ltd                     2.41   uncensored       1599   2026-09-04
   2   ...
   10  ...
   ---- remaining flagged ----
   11  ...
=====================================================================
 SECTION 2 - WHY EACH STOCK WAS CHOSEN (plain English)
 ---------------------------------------------------------------------
 #1  BSE - BSE Ltd
   In plain words: over recent weeks BSE kept making slightly lower price lows, but
   daily MACD momentum was already turning up (higher lows) - an early sign the fall
   is losing steam. That low landed inside BSE's weekly support band (the 11/22/50-week
   average zone), and momentum was not deeply oversold. The setup's conditions were met.
   What it satisfied (checks + numbers):
     1) Bullish divergence (daily): earlier dip 2026-08-21 (MACD hist -18.13, price low
        3223.00) -> latest dip 2026-09-02 (MACD hist -3.49, price low 3131.50): momentum
        made a HIGHER low while price made a LOWER low [OK]; latest dip confirmed (momentum
        turned back up) [OK].
     2) Weekly support zone (week ending 2026-09-04): weekly averages formed a band
        3178.3-3520.1; that week's range 3131.5-3474.0 overlapped it [OK].
     3) RSI health: RSI at the low = 33.29, at/above 30 -> "uncensored" (healthy dip) [OK].
     4) Liquidity: ₹1,599 cr traded/day (> ₹5 cr floor) -> tradeable.
   Why it ranks #1: strongest blend of momentum turn, tight support, healthy RSI, liquidity.
 ---------------------------------------------------------------------
 #2  ...
=====================================================================
 PENDING (weekly candle still forming - will confirm after the week closes): <symbols>
 NOTES
  • "censored" RSI = the dip broke below 30 (weaker) - the stock is STILL listed (RSI only
    labels, it never removes a stock).
  • Method: local-pivot troughs, TROUGH_PIVOT_K=3 (Rule Spec v1.2 §1.3). Every number above is
    computed from sourced data as of <DATE>. Not investment advice - verify each chart.
=====================================================================
```
**Single file per day (v1.5):** the report is the ONE deliverable file
`output/top_recommended_for_<DATE>.txt`, keyed on the data as-of date and **overwritten** on
re-run (the "Generated" timestamp inside updates). The run summary (counts, skips-by-reason,
fetch failures) is **folded into a SCAN SUMMARY section** of that file - no separate log file.
The machine-readable `output/flagged_<DATE>.csv` (every field per flagged stock, for audit) is
written **only when `[output] write_full_flagged_csv = true`** (default **false** → exactly one
file per day).

## 9. Edge cases & correctness rules
Warm-up (~6y) then slice last 60 - no truncated indicators • **causality:** ≥K bars after `recent`
(±K window fully known); never see beyond the as-of date • 60-bar boundary: detect on full series,
keep troughs whose *date* ∈ last 60 • closed-week rule §8.1 • insufficient history (< ~4y / 200
weekly bars, e.g. recent IPOs) → skip, protecting the weekly EMA50 zone (B1) • RSI 0/0 → 100 •
ties → earliest date / higher liquidity • **symbol renames → key on ISIN,
weekly `EQUITY_L` diff** • corporate actions consistent via weekly full refetch (splits/divs stored
for audit; rights approximate) • one bad symbol never aborts.

## 10. Build order
1. `requirements.txt` + `config.py`. 2. `indicators.py` + unit tests (§11). 3. `divergence.py`,
`zone.py`, `liquidity.py` + BSE fixture tests. 4. `universe.py`,`fetch.py`,`store.py` →
`scripts/fetch_data.py` (test on 3 symbols). 5. `rank.py`,`report.py` → `scripts/run_scanner.py`.
6. **Golden check** = BSE matches §4a/§8.7. 7. Full-universe run + README (Linux+Windows, schedule).

## 11. Validation & tests
- **Golden (pinned):** `research/validate_pipeline.py` - BSE must flag with the §4a values
  (Trough_prev 2026-08-21, Trough_recent 2026-09-02, week 2026-09-04, band [3178.3,3520.1],
  RSI 33.29 uncensored). The `src/` implementation must **reproduce this reference's outputs on the
  golden fixtures with the v1.2 fixes applied** (B1 history gate, B2 fetch counting, B3 NaN-safe
  ranking, closed-week) - **do not copy the reference code**, which still carries the latent issues
  those fixes address. *(The earlier `golden_test_bse.py` / `golden_test_variants.py` were
  exploratory and are superseded - keep for history, do not treat as spec.)*
- **Indicator unit tests** vs a small fixed input and vs TradingView values (±0.2%).
- **Truthfulness test:** parse the generated `top_recommended_for_<DATE>.txt` and assert every printed
  number (troughs, EMAs, band, RSI, liquidity, score) equals the value the pipeline computed for that
  stock - the report must contain zero hardcoded/placeholder data. For BSE it must print the real §4a
  values. Also assert every listed stock actually passed §8.2 **and** §8.3.
- **Determinism:** same data+config → identical `flagged_<DATE>.csv`.
- **Scale smoke test:** full-universe run (~90 min expected); eyeball 3–5 flagged charts on TV,
  **including ≥1 name with an in-window split/bonus** (adjustment correctness).
- **Cross-platform:** run both scripts on Linux and Windows; outputs identical.

## 12. Sign-off items (resolved vs. for the user)
**Superseded by Rule Spec v1.2 (see `v1.4 -> v1.5` changelog):** the trough definition is now the
local-pivot rule (§1.3, `TROUGH_PIVOT_K=3`), not prominence; `MIN_SEGMENT_LEN` and `min separation`
are removed. The confirmation + recency guards remain.
**Resolved (see §4/§4a + v1.2 changelog):** causality/confirmation, recency, closed-week (+residual noted),
ranking fixes, liquidity essential, **B1** weekly-history gate (≥200 weekly bars), **B2** unattended
fetch (0% real failure on 200 random EQ; failed-only failover; yfinance==1.7.0 + smoke-fetch; ISIN
rename tracking), **B3** NaN-safe ranking, feasibility (~88 min), yfinance 1.7.0 verified.
**For user confirmation before/at greenlight:**
1. **`TOLERANCE_PCT` = 1%** (D5) - confirm (vs 0.1% literal).
2. **Liquidity floor ₹5 cr/day + ₹20 min price** - confirm the tradeability bar (raise for stricter).
3. **Ranking weights** (§8.6) - confirm the six-metric composite and weights match your priorities
   (e.g., value momentum vs. support-confluence vs. liquidity differently?).
4. **Universe scope** - full EQ (default) or use `index_filter` (NIFTY500 etc.) for reliability/speed?
5. **Comparison scope** - RESOLVED in v1.2: the two most recent troughs, **no** separation guard (`DIVERGENCE_SCOPE` / `MIN_TROUGH_SEP` removed).
6. **Weekly zone leniency** - keep spec-literal wick-touch (default) or require Close/body in band?

**Remaining pre-implementation validation (do during build, not blocking greenlight):** TradingView
per-name cross-check on 3–5 corporate-action names (§11).

---
### Appendix A - parquet schema (`data/daily/<SYMBOL>.parquet`)
`date`(index) · `Open High Low Close`(split-adj, div-unadj Float) · `Volume`(Int) ·
`AdjClose Dividends StockSplits`(audit) · `source`(Str) · `fetched_at`. File meta: `symbol, isin,
adjustment="split_only"`.

### Appendix B - Script 2 pseudo-code
```
cfg=load_config()
for sym in manifest.status=="ok":
    d=load_parquet(sym)
    if daily_rows < min_rows_daily(1000) or weekly_bars < min_weekly_bars_for_zone(200): skip("insufficient_history")
    liq=median(Close*Volume, 20)
    if cfg.liquidity.apply_as_filter and (liq<min or last_close<min_price): skip("illiquid")
    H, rsi, atr = macd_hist(d.Close), wilder_rsi(d.Close), atr14(d)
    div = detect_divergence(d, H, cfg)          # pivot troughs (two most recent) + causality + confirmation + recency
    if not div.is_true: continue
    z = weekly_zone(weekly(d), div.swing_low_date, cfg)
    if z.status=="pending_week": pending.append(sym); continue
    if not z.zone_ok: continue
    rec.append(build_record(sym, div, z, rsi_tag(rsi,div.recent,cfg), liq, atr, vol_exp))
ranked = rank(rec, cfg.ranking)                 # z-score composite w/ small-cohort guard
write_txt(ranked[:top_n], ranked, pending, meta); write_csv(ranked); write_log(...)
```
```
```

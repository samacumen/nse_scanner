# NSE Stock Scanner

Scans every NSE stock (~2,000+) once a week and gives you the **10 best "bottoming" setups**, each
with a plain-English reason. Runs on **Windows and Linux**. Free data (Yahoo Finance).

## What it looks for
A stock is picked only if **all** of these are true:
1. **Daily bullish divergence** - comparing the **two most recent MACD-momentum dips of the last 60
   trading days**: price makes a lower (or equal) low, but the daily **MACD momentum makes a
   *higher* low** (selling may be running out of steam).
2. **Weekly support zone** - the price range of the week that low falls in touches the stock's
   **weekly EMA 11 / 22 / 50 band**.
3. **Tradeable** - enough daily turnover (default: at least Rs 5 crore/day and a price of Rs 20+).

Stocks that pass 1 and 2 but fail 3 are **not hidden**: they are listed separately at the end of the
report, with what each one fell short on, but never ranked.

It also tags each pick's **RSI health**: `uncensored` = the dip held at/above RSI 30 (healthier);
`censored` = it dipped below 30 (weaker). This is only a label; it never removes a stock.

## What you get
**One file per day**: `output/top_recommended_for_<date>.txt` (re-running the same day just
updates it - the "Generated" time inside changes, but it stays a single file). It contains:
1. **THE LIST** - ranked 1, 2, 3 ... (top 10 first, then any other qualifying names), each showing
   the two MACD-trough dates and the support-zone week so you can check it on a chart.
2. **WHY EACH WAS CHOSEN** - a simple explanation plus the exact numbers behind every check.
3. **PASSES THE SETUP BUT FAILS LIQUIDITY** - the setups that are too thinly traded, with the reason.
4. **SCAN SUMMARY** - how many were scanned and why the rest were not selected.
5. **APPENDIX** - every spec field (both dip dates and MACD values, both price lows, the zone week,
   the three weekly averages and RSI) for each of the too-thinly-traded setups.

The header counts every stock that passes the setup (the spec's flag): the ranked ones plus the
too-thinly-traded ones. A stock whose data ends on a different day than the rest is marked
"(data to <date>)".

The header's "Data as-of" date is the date most stocks' data actually ends on, with a count (Yahoo
sometimes publishes the newest day for only some stocks at first - if so, Step 1 warns you; re-run it
later with `refresh_if_older_than_hours = 0` in `advanced_config.txt` so every stock is downloaded
again, then set it back).

Optional: set `write_full_flagged_csv = true` in `config.txt` to also get a spreadsheet
`flagged_<date>.csv`. It is off by default, so you get just the one text file.

## One-time setup
Needs **Python 3.10+** installed.

**Windows** (in the project folder):
```
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```
**Linux / macOS**:
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## How to run it - two steps
**Step 1 - download the data** (grabs/refreshes all ~2,000 stocks; takes ~90 minutes):
- Windows: `.venv\Scripts\python scripts\fetch_data.py`
- Linux:   `.venv/bin/python scripts/fetch_data.py`

**Step 2 - analyze and get the report** (takes seconds):
- Windows: `.venv\Scripts\python scripts\run_scanner.py`
- Linux:   `.venv/bin/python scripts/run_scanner.py`

Open the report in the `output/` folder.

## Do I have to run Step 1 every time? No.
- **Step 1** downloads the market data (slow). Do it **once a week** to refresh (e.g. over the
  weekend after Friday's close). It only ever keeps **finished** candles: a download before the
  15:30 IST close drops that day's still-forming candle, and a week counts as finished once the
  data was downloaded after that week's Friday 15:30 IST close (so a Friday market holiday needs
  nothing special). A week that is not finished yet shows its stocks as **PENDING**. It also stays
  pending if Yahoo is late with that week's last day: for one stock (other stocks already have a
  later day that week), or for every stock (Step 1 then checks NSE's own daily file to tell a
  holiday from a late feed; if NSE can't be reached, Step 1 warns and the week is judged by the
  clock and the other stocks).
- If Step 1 is stopped midway, just run it again: files downloaded in the last 12 hours are
  reused (unless an NSE session has closed since then), everything else is downloaded fresh.
- **Step 2** reads that saved data and writes the report (fast). Run it **as often as you like** -
  it **never re-downloads**.
- So if you change a setting and want to re-analyze, **just run Step 2 again.**

## Disk usage and data freshness
- Each stock is stored as **one file** in `data/daily/`, **overwritten** on refresh - copies never
  pile up.
- Step 1 downloads up to **6 years** of history per stock. A stock needs at least about **1 year**
  (250 trading days and 50 weekly candles in total, so the 50-week average has about a year of data); any stock
  with less is **skipped**, so the scan is never run on thin data and never guesses. The whole
  universe is only about **150 MB**.
- Step 1 also **deletes files for stocks that are no longer in your universe** (delisted, renamed, or
  excluded by `index_filter`), so old data does not clog your disk. Testing subsets
  (`symbols_override` / `max_symbols`) never trigger this. To keep everything instead, set
  `prune_stale = false` in `advanced_config.txt`.

## Settings you can change (`config.txt`)
Open **`config.txt`** in any text editor (Notepad is fine), change a value after `=`, and save.
Blank = use the default. Lists are comma-separated (e.g. `BSE,RELIANCE`). This file holds just the
everyday settings:

| Setting | What it does | Default |
|---|---|---|
| `index_filter` | Blank = every stock. Or narrow to an index: `NIFTY50`, `NIFTY100`, `NIFTY500`, `SMALLCAP250` (join with `+`) - fewer, cleaner names and a faster run. | (blank) |
| `symbols_override` | Scan ONLY the symbols you list (e.g. `BSE,RELIANCE`). Great for a quick test. Blank = full scan. | (blank) |
| `max_symbols` | Blank = all. A number (e.g. `50`) scans only that many - handy for testing. | (blank) |
| `series` | NSE listing types to include. `EQ` = normal equities. | EQ |
| `include_sme` | Include tiny SME-board stocks. | false |
| `history_years` | Years of price history to download per stock. | 6 |
| `price_adjustment` | `split_only` matches TradingView; `total_return` includes dividends. | split_only |
| `min_median_traded_value_inr` | Ignore stocks trading less than this per day. `50000000` = Rs 5 crore/day. | 50000000 |
| `min_price` | Ignore cheap stocks below this price (avoids penny stocks). | 20 |
| `top_n` | How many top picks to highlight. | 10 |
| `min_score` | Blank = show every qualifying stock (never pad the list with weak ones). | (blank) |
| `write_full_flagged_csv` | `false` = one text report per day; `true` = also save a spreadsheet CSV. | false |

**Which step to re-run:** change `[universe]` or `[data]` -> **Step 1** then Step 2 (it changes the
downloaded data); change `[liquidity]`, `[ranking]` or `[output]` -> just **Step 2**.

## Advanced settings (`advanced_config.txt`) - you can ignore this
The rarely-changed settings that define the trading METHOD live in **`advanced_config.txt`**: the
MACD periods, the divergence internals, the RSI settings, the weekly support-zone rules, the ranking
weights, and download mechanics. The defaults are tested - you normally never touch this file, and
it is safe to **delete the whole file** (the same defaults still apply from the code). Re-run
**Step 2** after a change (the `[data]` knobs there apply on the next Step 1 download).

The file is fully commented; the ones you're most likely to care about:
| Setting (section) | What it does | Default |
|---|---|---|
| `lookback_days` (`[divergence]`) | Recent days searched for the pattern (~3 months). | 60 |
| `trough_pivot_k` (`[divergence]`) | Bars on each side of a momentum dip that must be higher for it to count as a trough (a wider window = fewer, more distinct troughs). | 3 |
| `tolerance_pct` (`[divergence]`) | How close two lows count as "equal" (a double bottom). `0.01` = 1%. | 0.01 |
| `zone_test` (`[weekly]`) | `range_overlap` (week only has to touch the band) or `close_in_band` (stricter). | range_overlap |
| `smoothing` (`[rsi]`) | `wilder` (matches TradingView) or `sma`. | wilder |
| `lower_band` (`[rsi]`) | Oversold line for the `censored` / `uncensored` label. | 30 |
| `weight_*` (`[ranking]`) | How much each quality counts (momentum, zone, RSI, liquidity, recency, volume). | see file |
| `request_throttle_sec` (`[data]`) | Pause between downloads; raise if Yahoo rate-limits you. | 0.5 |

Every remaining knob - MACD `fast`/`slow`/`signal`, `price_window_k`, `price_field`,
`ema_set`, `min_weekly_bars_for_zone`, RSI `period`, `min_rows_daily`, `refresh_if_older_than_hours`,
output `dir` - is in `advanced_config.txt` with a one-line explanation. Fresher setups rank higher
(the `recency` weight), but age never removes a setup: any pair of dips inside the 60-day window counts.

## Quick test (a few seconds)
Set `symbols_override = BSE,RELIANCE,FEDERALBNK` in `config.txt`, then run Step 1 and Step 2.
You'll get a report for just those names. Set it back to blank for the full scan.

---
*Not investment advice. Every number in the report is computed from the downloaded data - always
check the chart before acting.*

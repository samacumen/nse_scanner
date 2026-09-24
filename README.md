# NSE Stock Scanner

Scans every NSE stock (~2,300) once a week and gives you the **10 best "bottoming" setups** plus
every other stock that passes the rules, each with the dates and numbers you need to check it on a
chart. Runs on **Windows 11 and Linux**. Free data (Yahoo Finance).

The rules come from the trader's spec, `prompts/NSE Scanner Rule Spec v1.2.docx`; the full design
notes are in `inputs/BLUEPRINT.md`.

## What it looks for
A stock **passes the setup** (the spec's flag) when both of these are true:
1. **Daily bullish divergence** - comparing the **two most recent MACD-momentum dips of the last 60
   trading days**: price makes a lower (or equal, within 1%) low, but the daily **MACD momentum
   makes a *higher* low** (selling may be running out of steam).
2. **Weekly support zone** - the price range of the week that low falls in touches the stock's
   **weekly EMA 11 / 22 / 50 band**.

Stocks that pass are then sorted by **tradeability**: at least Rs 5 crore traded per day and a
price of Rs 20+ gets them **ranked** (top 10 first). Thinly traded ones are **not hidden** - they
get their own section, with what they fall short on, but are not ranked.

Every stock that passes also gets the spec's **RSI check**, a label and never a filter: take the
lowest RSI within 3 trading days of the recent MACD dip - `uncensored` means it stayed at/above 30
(a healthier dip), `censored` means it fell below 30 (oversold, a weaker sign).

## What you get
**One text file per day**: `output/top_recommended_for_<date>.txt` (re-running on the same data just
rewrites it). It reads top to bottom, with a gap between sections:
- **AT A GLANCE** - how many stocks pass the setup, how many are ranked, thinly traded or waiting.
- **HOW TO READ** - a short key to every column (dips, zone week, RSI check, score, turnover).
- **Section 1 - Top 10**: one line each - the two MACD-dip dates and the zone week (to check on
  TradingView), the RSI check, the score and the daily turnover.
- **Section 2 - Why the top 10**: each one in plain words, with the numbers behind every check.
- **Section 3 - Other tradeable setups** (#11 onwards): the same summary line, plus a second line
  with the spec's numbers (MACD at both dips, both price lows with dates, the zone week's price
  range and the weekly EMAs).
- **Section 4 - Waiting**: stocks whose price low is in a week that has not closed yet. The spec
  only judges a finished weekly candle, so they are re-checked on the next download (normally after
  Friday's 15:30 IST close).
- **Section 5 - Thinly traded setups**: pass the setup but fail the liquidity floor; same two lines
  per stock plus what each one falls short on.
- **Scan summary** (why the other stocks were not selected), **settings used** and **notes**.

The header's "Data to" date is the date most stocks' data actually ends on, with a count; a stock
whose data ends on another date is marked "(data to <date>)".

Optional: set `write_full_flagged_csv = true` in `config.txt` to also get a spreadsheet
`flagged_<date>.csv` with every stock that passes (a `ranked` column tells them apart). It is off by
default, so you get just the one text file.

## One-time setup
Needs **Python 3.10 or newer**.

**Windows 11** - open *Command Prompt* or *PowerShell* in the project folder:
```
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```
(If `py` is not found, install Python from python.org and tick "Add python.exe to PATH".)

**Linux / macOS**:
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## How to run it - two steps
**Step 1 - download the data** (all ~2,300 stocks; about 1 to 1.5 hours, depending on the connection):
- Windows: `.venv\Scripts\python scripts\fetch_data.py`
- Linux:   `.venv/bin/python scripts/fetch_data.py`

**Step 2 - analyze and write the report** (under a minute):
- Windows: `.venv\Scripts\python scripts\run_scanner.py`
- Linux:   `.venv/bin/python scripts/run_scanner.py`

Open the report in the `output/` folder.

## The weekly routine (and when to re-run what)
- Run **Step 1 once a week, after Friday's close** (e.g. on the weekend), then **Step 2**.
- **Step 2** only reads the saved data - run it as often as you like; after changing a setting,
  just run Step 2 again.
- Step 1 only ever keeps **finished** candles: a download before the 15:30 IST close drops that
  day's still-forming candle, and a week counts as finished once the data was downloaded after
  that week's Friday 15:30 IST close (a Friday market holiday needs nothing special).
- If Yahoo is late with a day - for some stocks, or for all of them (Step 1 then checks NSE's own
  daily file) - the affected week stays in **Waiting** until the data is complete, and Step 1 prints
  a warning. If NSE's file can't be reached, the week is judged by the clock and the other stocks,
  and the report says so. To force a full re-download, set `refresh_if_older_than_hours = 0` in
  `advanced_config.txt` for one run, then set it back.
- If Step 1 is stopped midway, just run it again: files downloaded in the last 12 hours are reused
  (unless an NSE session has closed since), everything else is downloaded fresh.

## Disk usage and data quality
- Each stock is **one file** in `data/daily/`, overwritten on every refresh; the whole universe is
  about **130 MB**.
- Step 1 downloads up to **6 years** per stock. A stock needs at least about **1 year** (250
  trading days and 50 weekly candles); newer listings are skipped, never guessed.
- Yahoo adds flat, zero-volume **filler rows** on NSE holidays (and on days a thinly traded stock
  had no trades). The scanner drops them, so every bar it uses is a real trading session - as on
  TradingView.
- Step 1 deletes files for stocks that left your universe (delisted, renamed, or outside your
  `index_filter`). Testing subsets (`symbols_override` / `max_symbols`) never trigger this. To keep
  everything, set `prune_stale = false` in `advanced_config.txt`.

## Settings you can change (`config.txt`)
Open **`config.txt`** in any text editor (Notepad is fine), change a value after `=`, and save.
Blank = use the default. Lists are comma-separated (e.g. `BSE,RELIANCE`).

| Setting | What it does | Default |
|---|---|---|
| `index_filter` | Blank = every stock. Or narrow to an index: `NIFTY50`, `NIFTY100`, `NIFTY500`, `SMALLCAP250` (join with `+`). | (blank) |
| `symbols_override` | Scan ONLY the symbols you list (e.g. `BSE,RELIANCE`) - great for a quick test. | (blank) |
| `max_symbols` | Blank = all. A number (e.g. `50`) scans only that many - handy for testing. | (blank) |
| `series` | NSE listing types to include. `EQ` = normal equities. | EQ |
| `include_sme` | Include tiny SME-board stocks. | false |
| `history_years` | Years of price history to download per stock. | 6 |
| `price_adjustment` | `split_only` matches TradingView; `total_return` also adjusts for dividends. | split_only |
| `min_median_traded_value_inr` | Liquidity floor per day. `50000000` = Rs 5 crore/day. | 50000000 |
| `min_price` | Price floor (avoids penny stocks). | 20 |
| `top_n` | How many top picks get the plain-words write-up. | 10 |
| `write_full_flagged_csv` | `true` = also save a spreadsheet CSV. | false |

**Which step to re-run:** change `[universe]` or `[data]` -> **Step 1** then Step 2; change
`[liquidity]`, `[ranking]` or `[output]` -> just **Step 2**.

## Advanced settings (`advanced_config.txt`) - you can ignore this
The settings that define the trading METHOD live in **`advanced_config.txt`**. The defaults follow
the spec; you normally never touch this file, and it is safe to **delete it** (the same defaults
apply from the code). Re-run **Step 2** after a change (its `[data]` settings apply on the next
Step 1).

The ones you're most likely to care about:
| Setting (section) | What it does | Default |
|---|---|---|
| `lookback_days` (`[divergence]`) | Recent trading days searched for the pattern (~3 months). | 60 |
| `trough_pivot_k` (`[divergence]`) | Bars on each side that must be at/above a momentum dip for it to count. | 3 |
| `tolerance_pct` (`[divergence]`) | How close two lows count as "equal" (a double bottom). `0.01` = 1%. | 0.01 |
| `zone_test` (`[weekly]`) | `range_overlap` (the week only has to touch the band) or `close_in_band` (stricter). | range_overlap |
| `smoothing` (`[rsi]`) | `wilder` (TradingView's default) or `sma`. | wilder |
| `lower_band` (`[rsi]`) | The line for the `censored` / `uncensored` RSI check. | 30 |
| `apply_as_filter` (`[liquidity]`) | `false` = rank every stock that passes, however thinly traded. | true |
| `weight_*` (`[ranking]`) | How much each quality counts in the score (momentum, zone, RSI, liquidity, freshness, volume). | see file |
| `request_throttle_sec` (`[data]`) | Pause between downloads; raise it if Yahoo rate-limits you. | 0.5 |

Every other setting - MACD `fast`/`slow`/`signal`, `price_window_k`, `price_field`, `ema_set`,
`min_weekly_bars_for_zone`, RSI `period`, liquidity `window`, `min_rows_daily`,
`refresh_if_older_than_hours`, `prune_stale`, output `dir` - is in the file with a one-line
explanation. Fresher setups rank higher, but age never removes a setup: any pair of dips inside
the 60-day window counts.

## Windows 11 notes
- Both Command Prompt and PowerShell work with the commands above; nothing needs admin rights.
- The report is plain text: open it in Notepad and, for the wide tables, turn off word wrap
  (**View > Word wrap** in Windows 11 Notepad; **Format > Word Wrap** in older versions).
- Close any file from the `data/` or `output/` folders that is open in Excel before running Step 1 or
  Step 2 (Excel locks open files, so they can't be rewritten).
- Keep the PC awake during Step 1 (1 to 1.5 hours); if it sleeps or stops, just run Step 1 again -
  it resumes.
- `config.txt` can be saved from Notepad in any UTF-8 form (with or without "BOM").

## Quick test (a few seconds)
Set `symbols_override = BSE,RELIANCE,FEDERALBNK` in `config.txt`, then run Step 1 and Step 2.
You'll get a report for just those names. Set it back to blank (and run Step 1 again) for the full
scan.

---
*Not investment advice. Every number in the report is computed from the downloaded data - always
check the chart before acting.*

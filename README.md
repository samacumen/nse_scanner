# NSE Stock Scanner

Scans every NSE stock (~2,000+) once a week and gives you the **10 best "bottoming" setups**, each
with a plain-English reason. Runs on **Windows and Linux**. Free data (Yahoo Finance).

## What it looks for
A stock is picked only if **all** of these are true:
1. **Daily bullish divergence** — price makes a lower (or equal) low, but the daily **MACD momentum
   makes a *higher* low** (selling may be running out of steam), and momentum has turned back up.
2. **Weekly support zone** — that low sits inside the stock's **weekly EMA 11 / 22 / 50 band**.
3. **Tradeable** — enough daily turnover (default: at least Rs 5 crore/day).

It also tags each pick's **RSI health**: `uncensored` = the dip held at/above RSI 30 (healthier);
`censored` = it dipped below 30 (weaker). This is only a label; it never removes a stock.

## What you get
**One file per day**: `output/top_recommended_for_<date>.txt` (re-running the same day just
updates it — the "Generated" time inside changes, but it stays a single file). It contains:
1. **THE LIST** — ranked 1, 2, 3 ... (top 10 first, then any other qualifying names).
2. **WHY EACH WAS CHOSEN** — a simple explanation plus the exact numbers behind every check.
3. **SCAN SUMMARY** — how many were scanned and why the rest were not selected.

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
  weekend after Friday's close).
- **Step 2** reads that saved data and writes the report (fast). Run it **as often as you like** -
  it **never re-downloads**.
- So if you change a setting and want to re-analyze, **just run Step 2 again.**

## Change the criteria (no coding)
Open **`config.txt`** in any text editor, change a value, save, and re-run **Step 2**. Handy ones:
- `top_n` - how many top picks (default 10)
- `min_median_traded_value_inr` - liquidity floor (default 50000000 = Rs 5 cr/day)
- `tolerance_pct` - how close two lows count as "equal" (default 0.01 = 1%)
- `index_filter` - leave blank for all stocks, or e.g. `NIFTY500` for fewer, cleaner names
- `symbols_override` - put a few symbols (e.g. `BSE,RELIANCE`) to test on just those

Settings under **`[macd]` ... `[output]`** only need **Step 2**. Settings under **`[universe]` /
`[data]`** need **Step 1** again (they change what/how data is downloaded).

## Quick test (a few seconds)
Set `symbols_override = BSE,RELIANCE,FEDERALBNK` in `config.txt`, then run Step 1 and Step 2.
You'll get a report for just those names. Set it back to blank for the full scan.

---
*Not investment advice. Every number in the report is computed from the downloaded data - always
check the chart before acting.*

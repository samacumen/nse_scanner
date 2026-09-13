# NSE Stock Scanner

Scans every NSE stock (~2,000+) once a week and gives you the **10 best "bottoming" setups**, each
with a plain-English reason. Runs on **Windows and Linux**. Free data (Yahoo Finance).

## What it looks for
A stock is picked only if **all** of these are true:
1. **Daily bullish divergence** - price makes a lower (or equal) low, but the daily **MACD momentum
   makes a *higher* low** (selling may be running out of steam), and momentum has turned back up.
2. **Weekly support zone** - that low sits inside the stock's **weekly EMA 11 / 22 / 50 band**.
3. **Tradeable** - enough daily turnover (default: at least Rs 5 crore/day).

It also tags each pick's **RSI health**: `uncensored` = the dip held at/above RSI 30 (healthier);
`censored` = it dipped below 30 (weaker). This is only a label; it never removes a stock.

## What you get
**One file per day**: `output/top_recommended_for_<date>.txt` (re-running the same day just
updates it - the "Generated" time inside changes, but it stays a single file). It contains:
1. **THE LIST** - ranked 1, 2, 3 ... (top 10 first, then any other qualifying names).
2. **WHY EACH WAS CHOSEN** - a simple explanation plus the exact numbers behind every check.
3. **SCAN SUMMARY** - how many were scanned and why the rest were not selected.

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

## Settings you can change (`config.txt`) - no coding
Open **`config.txt`** in any text editor (Notepad is fine), change a value after the `=`, and save.
Blank means "use the default / no limit". Lists are comma-separated (e.g. `BSE,RELIANCE`).

**Two kinds of settings - which step to re-run after a change:**
- Change anything in **`[universe]`** or **`[data]`** -> re-run **Step 1** (it changes what data is
  downloaded), then Step 2.
- Change anything else (`[macd]` through `[output]`) -> just re-run **Step 2** (instant, no
  re-download).

### Start here (the settings most people touch)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `top_n` | How many top picks to highlight at the top of the list. | 10 |
| `min_median_traded_value_inr` | Ignore stocks that trade less than this much per day (rupees). `50000000` = Rs 5 crore/day. Raise it to keep only very liquid names. | 50000000 |
| `min_price` | Ignore cheap stocks below this price (avoids penny stocks). | 20 |
| `index_filter` | Blank = scan every stock. Or narrow to an index: `NIFTY50` (50 biggest), `NIFTY100`, `NIFTY500`, or `SMALLCAP250` - fewer, cleaner names and a faster run. | (blank) |
| `symbols_override` | Scan ONLY the symbols you list here (e.g. `BSE,RELIANCE`). Great for a quick test. Blank = full scan. | (blank) |
| `write_full_flagged_csv` | `false` = one text report per day. `true` = also save a spreadsheet (`.csv`). | false |

Everything below has a sensible default; you can safely ignore it until you want to fine-tune.

### `[universe]` - which stocks to scan (needs Step 1)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `series` | NSE listing types to include. `EQ` = normal equities (what you want). | EQ |
| `include_sme` | Include tiny SME-board stocks. Usually leave off. | false |
| `index_filter` | Blank = all stocks. Or an index list: `NIFTY50`, `NIFTY100`, `NIFTY500`, `SMALLCAP250` (join with `+`, e.g. `NIFTY500+SMALLCAP250`). | (blank) |
| `max_symbols` | Blank = all. A number (e.g. `50`) scans only that many - handy for testing. | (blank) |
| `symbols_override` | Scan ONLY these symbols. Blank = normal full scan. | (blank) |

### `[data]` - how prices are downloaded (needs Step 1)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `history_years` | Years of price history to download per stock. More = steadier weekly averages. | 6 |
| `price_adjustment` | `split_only` matches TradingView charts. `total_return` also includes dividends. | split_only |
| `request_throttle_sec` | Pause between downloads. Raise it (e.g. `1.0`) if Yahoo starts blocking you. | 0.5 |
| `min_rows_daily` | Least history a stock needs or it's skipped (new listings). ~1000 = about 4 years. | 1000 |
| `refresh_if_older_than_hours` | Re-use files newer than this so you can resume a run. `0` = always re-download. | 120 |

### `[macd]` - the momentum indicator (Step 2)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `fast` / `slow` / `signal` | The standard MACD settings. Leave as-is unless you know MACD well. | 12 / 26 / 9 |

### `[divergence]` - Check 1: the daily "momentum turning up" pattern (Step 2)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `lookback_days` | Recent trading days to search for the pattern. 60 is about 3 months. | 60 |
| `price_window_k` | Days on each side of a dip used to find its true low price. | 3 |
| `trough_detection` | How momentum dips are found. `prominence` is the tested default; `strict` is the literal textbook rule. | prominence |
| `min_segment_len` | (advanced) smallest momentum-dip width that counts. | 1 |
| `prominence_frac` | How pronounced a momentum dip must be to count. Higher = stricter, fewer picks. | 0.10 |
| `divergence_scope` | Compare the latest dip to the previous one (`two_most_recent`) or to the deepest earlier one. | two_most_recent |
| `min_trough_sep` | Fewest days apart the two compared dips must be. | 7 |
| `tolerance_pct` | How close two lows count as "equal" (a double bottom). `0.01` = within 1%. | 0.01 |
| `price_field` | Which price to compare for a "lower low": the day's `Low` or its `Close`. | Low |
| `require_confirmation` | Only pick once momentum has actually turned back up (avoids catching a falling knife). | true |
| `confirm_bars` | How many rising days count as "turned back up." | 3 |
| `recency_bars` | The recent dip must be within this many days of now (keeps picks fresh). | 20 |

### `[weekly]` - Check 2: the weekly support zone (Step 2)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `ema_set` | The three weekly moving averages that form the support band. | 11,22,50 |
| `zone_test` | `range_overlap` = the week only has to touch the band (looser). `close_in_band` = it must close inside (stricter). | range_overlap |
| `min_weekly_bars_for_zone` | Weeks of history needed for the 50-week average to be trustworthy (~4 years). | 200 |

### `[rsi]` - Check 3: the "healthy dip" label (Step 2; labels only, never filters)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `period` | RSI length. 14 is standard. | 14 |
| `smoothing` | `wilder` matches TradingView's RSI; `sma` is a simpler variant. | wilder |
| `lower_band` | The oversold line. At/above = `uncensored` (healthier); below = `censored`. | 30 |

### `[liquidity]` - keep only tradeable stocks (Step 2)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `apply_as_filter` | Turn the liquidity filter on/off. | true |
| `window` | Days used to measure average turnover. | 20 |
| `min_median_traded_value_inr` | Minimum average daily turnover in rupees. `50000000` = Rs 5 crore/day. | 50000000 |
| `min_price` | Ignore stocks below this price. | 20 |

### `[ranking]` - how the top 10 is ordered (Step 2)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `top_n` | How many top picks to highlight. | 10 |
| `weight_momentum` | How much a strong momentum turn counts in the ranking. | 0.30 |
| `weight_zone_confluence` | How much a tight, well-centred support zone counts. | 0.20 |
| `weight_rsi_quality` | How much a healthy (higher) RSI counts. | 0.15 |
| `weight_liquidity` | How much higher turnover counts. | 0.15 |
| `weight_recency` | How much a fresher signal counts. | 0.10 |
| `weight_volume_expansion` | How much a jump in volume counts. | 0.10 |
| `min_score` | A quality floor. Blank = show every qualifying stock (never pad the list with weak ones). | (blank) |

*(The weights are relative - bigger means more influence. They do not need to add up to 1.)*

### `[output]` - the report file (Step 2)
| Setting | Plain-English meaning | Default |
|---|---|---|
| `dir` | Folder where the report is written. | output |
| `write_full_flagged_csv` | `false` = one text file per day; `true` = also write a spreadsheet CSV. | false |

## Quick test (a few seconds)
Set `symbols_override = BSE,RELIANCE,FEDERALBNK` in `config.txt`, then run Step 1 and Step 2.
You'll get a report for just those names. Set it back to blank for the full scan.

---
*Not investment advice. Every number in the report is computed from the downloaded data - always
check the chart before acting.*

"""
GOLDEN TEST - BSE Ltd (the spec's own diagram example).

Purpose: reproduce the full NSE Scanner Rule Spec v1.1 pipeline on the one stock
we KNOW should flag (BSE Ltd, shown in the spec's TradingView screenshot), and in
particular determine whether the LITERAL trough definition (one trough per maximal
H<0 segment -> two troughs require a zero-cross between them) reproduces the
divergence, versus a PROMINENCE-based sub-trough definition.

This is a DIAGNOSTIC, not product code. Decisions locked with the user:
  - Feed: yfinance (.NS), split/bonus-adjusted, dividend-UNadjusted (auto_adjust=False, raw OHLC).
  - RSI: Wilder's RMA(14).
  - Weekly zone: swing-low date's week, closed weeks only.
  - Confirmation: recent negative segment must have turned back up.
Defaults from spec: MACD 12/26/9, LOOKBACK_DAYS=60, K=3, MIN_SEGMENT_LEN=2,
weekly EMA 11/22/50, TOLERANCE_PCT=0.1%, RSI_LOWER_BAND=30.
"""
import sys, json, urllib.request
import numpy as np
import pandas as pd

TICKER = "BSE.NS"
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
LOOKBACK_DAYS = 60
K = 3
MIN_SEGMENT_LEN = 2
TOLERANCE_PCT = 0.001
RSI_PERIOD = 14
RSI_LOWER_BAND = 30
WEEKLY_EMAS = (11, 22, 50)

# ----------------------------------------------------------------------------- fetch
def fetch_yf():
    import yfinance as yf
    df = yf.download(TICKER, period="3y", interval="1d",
                     auto_adjust=False, actions=True, progress=False, threads=False)
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)
    return df

def fetch_direct():
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}"
           f"?range=3y&interval=1d&events=div%2Csplits")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=20))
    res = d["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata").normalize().tz_localize(None)
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"Open": q["open"], "High": q["high"], "Low": q["low"],
                       "Close": q["close"], "Volume": q["volume"]}, index=ts)
    splits = res.get("events", {}).get("splits", {})
    df.attrs["splits"] = splits
    return df.dropna(subset=["Close"])

def load():
    src = "yfinance(auto_adjust=False)"
    try:
        df = fetch_yf()
        if df is None or len(df) < 200:
            raise RuntimeError("yfinance returned too little; falling back")
    except Exception as e:
        print(f"[fetch] yfinance failed ({e.__class__.__name__}: {str(e)[:80]}); using direct chart API")
        df = fetch_direct()
        src = "direct-chart-api"
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
    df.index = pd.to_datetime(df.index)
    return df, src

# ------------------------------------------------------------------------- indicators
def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def macd_hist(close):
    line = ema(close, MACD_FAST) - ema(close, MACD_SLOW)
    signal = ema(line, MACD_SIGNAL)
    return line, signal, line - signal

def wilder_rsi(close, period=RSI_PERIOD):
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)

# --------------------------------------------------------------------- trough finders
def troughs_strict(H):
    """One trough per maximal H<0 run with run-length >= MIN_SEGMENT_LEN. (spec literal)"""
    h = H.values
    out = []
    i, n = 0, len(h)
    while i < n:
        if np.isnan(h[i]) or h[i] >= 0:
            i += 1; continue
        j = i
        while j < n and h[j] < 0:
            j += 1
        seg = range(i, j)          # [i, j) is one maximal negative run
        if (j - i) >= MIN_SEGMENT_LEN:
            k = min(seg, key=lambda x: h[x])
            out.append(k)
        i = j
    return out

def troughs_prominence(H, min_gap=2):
    """Local minima of H below zero (allows >1 sub-trough inside one negative run)."""
    h = H.values
    out = []
    for i in range(1, len(h) - 1):
        if np.isnan(h[i]) or h[i] >= 0:
            continue
        if h[i] <= h[i-1] and h[i] < h[i+1]:
            out.append(i)
    # enforce a minimal separation, keeping the deeper of two too-close minima
    pruned = []
    for i in out:
        if pruned and (i - pruned[-1]) < min_gap:
            if h[i] < h[pruned[-1]]:
                pruned[-1] = i
        else:
            pruned.append(i)
    return pruned

def price_low(df, t):
    lo = max(0, t - K); hi = min(len(df) - 1, t + K)
    win = df["Low"].iloc[lo:hi+1]
    return float(win.min()), win.idxmin()

def rsi_trough(rsi, t):
    lo = max(0, t - K); hi = min(len(rsi) - 1, t + K)
    return float(rsi.iloc[lo:hi+1].min())

# ---------------------------------------------------------------------------- evaluate
def evaluate(df, H, rsi, trough_idx, label):
    n = len(df)
    window_start = n - LOOKBACK_DAYS
    recent = [t for t in trough_idx if t >= window_start]
    print(f"\n=== {label} ===")
    print(f"  troughs in last {LOOKBACK_DAYS} bars: {len(recent)}")
    for t in recent:
        pl, pld = price_low(df, t)
        print(f"    idx {t:>3}  {df.index[t].date()}  H={H.iloc[t]:+.3f}  "
              f"priceLow(±{K})={pl:.2f} @ {pld.date()}")
    if len(recent) < 2:
        print("  -> < 2 troughs -> NO DIVERGENCE")
        return None
    t_prev, t_recent = recent[-2], recent[-1]
    h_prev, h_recent = float(H.iloc[t_prev]), float(H.iloc[t_recent])
    pl_prev, pld_prev = price_low(df, t_prev)
    pl_recent, pld_recent = price_low(df, t_recent)
    momentum = h_recent > h_prev
    price_ok = pl_recent <= pl_prev * (1 + TOLERANCE_PCT)
    diverg = momentum and price_ok
    # confirmation: has H turned back up after t_recent?
    after = H.iloc[t_recent+1:]
    confirmed = bool((after > 0).any()) or (len(after) >= K and (after.diff().dropna().head(K) > 0).all())
    print(f"  Trough_prev  : {df.index[t_prev].date()} H={h_prev:+.3f} priceLow={pl_prev:.2f}")
    print(f"  Trough_recent: {df.index[t_recent].date()} H={h_recent:+.3f} priceLow={pl_recent:.2f}")
    print(f"  momentum higher-low (H_recent>H_prev): {momentum}")
    print(f"  price lower/equal-low (<= prev*(1+{TOLERANCE_PCT})): {price_ok} "
          f"(recent {pl_recent:.2f} vs thresh {pl_prev*(1+TOLERANCE_PCT):.2f})")
    print(f"  >>> DIVERGENCE = {diverg}   | recent-dip confirmed(turned up)= {confirmed}")
    if diverg:
        rtv = rsi_trough(rsi, t_recent)
        print(f"  RSI_trough_value(±{K}, Wilder) = {rtv:.2f} -> "
              f"{'uncensored' if rtv >= RSI_LOWER_BAND else 'censored'}")
        return {"t_recent": t_recent, "swing_low_date": pld_recent, "diverg": True}
    return {"diverg": False}

def weekly_zone(df, swing_low_date):
    wk = df.resample("W-FRI").agg(Open=("Open","first"), High=("High","max"),
                                  Low=("Low","min"), Close=("Close","last"),
                                  Volume=("Volume","sum")).dropna(subset=["Close"])
    # closed weeks only: drop the still-forming current week
    last_daily = df.index[-1]
    wk = wk[wk.index <= last_daily]  # W-FRI label is week-end (Fri); keep all, then pick bucket
    emas = {p: ema(wk["Close"], p) for p in WEEKLY_EMAS}
    # weekly bucket containing swing_low_date = first week-end label >= swing_low_date
    cand = wk.index[wk.index >= pd.Timestamp(swing_low_date)]
    if len(cand) == 0:
        print("  [weekly] swing-low week not closed yet -> WAIT (per 'closed only' choice)")
        return
    W = cand[0]
    e = {p: float(emas[p].loc[W]) for p in WEEKLY_EMAS}
    lo, hi = min(e.values()), max(e.values())
    row = wk.loc[W]
    zone_ok = (row["Low"] <= hi) and (row["High"] >= lo)
    print(f"\n=== WEEKLY EMA ZONE (candle W ending {W.date()}) ===")
    print(f"  EMA11={e[11]:.1f} EMA22={e[22]:.1f} EMA50={e[50]:.1f}  band=[{lo:.1f},{hi:.1f}]")
    print(f"  Week Low={row['Low']:.1f} High={row['High']:.1f}  -> zone_ok={zone_ok}")

def main():
    df, src = load()
    print(f"[fetch] source={src}  bars={len(df)}  range={df.index[0].date()}..{df.index[-1].date()}")
    line, signal, H = macd_hist(df["Close"])
    rsi = wilder_rsi(df["Close"])
    # show recent structure to eyeball vs the diagram
    tail = pd.DataFrame({"Close": df["Close"], "Low": df["Low"],
                         "H": H, "sign": np.sign(H)}).tail(45)
    with pd.option_context("display.max_rows", 60, "display.width", 120):
        print("\n--- last 45 daily bars (Close / Low / MACD-hist H / sign) ---")
        print(tail.round(3).to_string())
    r_strict = evaluate(df, H, rsi, troughs_strict(H), "STRICT (spec literal: 1 trough / neg-segment)")
    r_prom   = evaluate(df, H, rsi, troughs_prominence(H), "PROMINENCE (sub-troughs within a neg-run)")
    for r in (r_strict, r_prom):
        if r and r.get("diverg"):
            weekly_zone(df, r["swing_low_date"]); break

if __name__ == "__main__":
    main()

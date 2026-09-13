"""
VALIDATION harness (pre-implementation). Pins ONE production-grade pipeline and:
  1) re-validates BSE at full 6y warm-up -> emits the REAL golden numbers for the blueprint,
  2) runs a multi-symbol DRY RUN -> fetch reliability, timing, flag-rate sanity, adjustment check.

Addresses expert punch-list: true topographic prominence via scipy.find_peaks (P0-1),
causality+confirmation fix (P0-3), min-separation (P1-8), NSE-cal-robust closed week (P1-9),
tolerance 1% (P2-11), recency guard (P1-5). This is a DIAGNOSTIC in research/, not the
deliverable src/ scripts (those are written only after user greenlight).

Usage:
  python validate_pipeline.py bse
  python validate_pipeline.py basket [N_RANDOM]
"""
import sys, time, json, urllib.request
import numpy as np, pandas as pd
from scipy.signal import find_peaks

# ---- locked/spec params (+ expert-revised defaults being validated) ----
MACD=(12,26,9); LOOKBACK=60; K=3; MIN_SEG=1   # prominence (not seg-len) is the noise filter
PROM_FRAC=0.10; PROM_SCALE="max"        # threshold = PROM_FRAC * scale(|H| over window)
MIN_TROUGH_SEP=2*K+1                     # >=7 bars between the two compared troughs (P1-8)
DIST=3                                    # find_peaks min spacing (dedupe adjacent minima)
TOL=0.01                                  # 1% "equal low" (P2-11, revised from 0.1%)
CONFIRM_BARS=3; RECENCY_BARS=20           # recent trough must be <=20 bars old (P1-5)
RSI_P=14; RSI_LB=30; WK_EMAS=(11,22,50)
LIQ_WIN=20; LIQ_MIN=5e7                   # ₹5 cr/day median (P1-6)
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36","Accept":"application/json"}

# ---------------------------------------------------------------- fetch (yf + fallback)
def fetch(sym, years=6):
    import yfinance as yf
    try:
        df=yf.download(f"{sym}.NS",period=f"{years}y",interval="1d",
                       auto_adjust=False,actions=True,progress=False,threads=False)
        if df is not None and len(df)>200:
            if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
            df=df.rename(columns=str.title)
            out=df[["Open","High","Low","Close","Volume"]].dropna(subset=["Close"]).copy()
            return out,"yfinance"
    except Exception: pass
    url=(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS"
         f"?range={years}y&interval=1d&events=splits")
    d=json.load(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=25))
    res=d["chart"]["result"][0]
    idx=pd.to_datetime(res["timestamp"],unit="s",utc=True).tz_convert("Asia/Kolkata").normalize().tz_localize(None)
    q=res["indicators"]["quote"][0]
    df=pd.DataFrame({"Open":q["open"],"High":q["high"],"Low":q["low"],"Close":q["close"],
                     "Volume":q["volume"]},index=idx).dropna(subset=["Close"])
    return df,"chart-api"

# ---------------------------------------------------------------- indicators
def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def macd_hist(c):
    line=ema(c,MACD[0])-ema(c,MACD[1]); sig=ema(line,MACD[2]); return line-sig
def wilder_rsi(c,p=RSI_P):
    d=c.diff(); g=d.clip(lower=0); l=(-d).clip(lower=0)
    ag=g.ewm(alpha=1/p,adjust=False).mean(); al=l.ewm(alpha=1/p,adjust=False).mean()
    rs=ag/al.replace(0,np.nan); r=100-100/(1+rs)
    return r.fillna(100.0)  # 0/0 flat -> 100 (P2-13 guard)
def atr(df,p=14):
    h,l,c=df["High"],df["Low"],df["Close"]; pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/p,adjust=False).mean()

# ---------------------------------------------------------------- troughs (true prominence)
def neg_run_len(h,i):
    if h[i]>=0: return 0
    l=i
    while l-1>=0 and h[l-1]<0: l-=1
    r=i
    while r+1<len(h) and h[r+1]<0: r+=1
    return r-l+1
def find_troughs(H):
    h=H.values; n=len(h); w=h[max(0,n-LOOKBACK):]
    scale=np.nanmax(np.abs(w)) if PROM_SCALE=="max" else np.nanmedian(np.abs(w[w<0]) if (w<0).any() else [1])
    min_prom=PROM_FRAC*(scale if scale and not np.isnan(scale) else 1.0)
    peaks,_=find_peaks(-h,prominence=min_prom,distance=DIST)   # minima of h w/ topographic prominence
    return [int(p) for p in peaks if h[p]<0 and neg_run_len(h,p)>=MIN_SEG]

def price_low(df,t):
    lo=max(0,t-K); hi=min(len(df)-1,t+K); win=df["Low"].iloc[lo:hi+1]
    return float(win.min()), win.idxmin()

def detect(df,H):
    n=len(df); tr=[t for t in find_troughs(H) if t>=n-LOOKBACK]
    if len(tr)<2: return None
    # recent = latest trough with >=K bars after it (causality) and within recency window
    rec=None
    for t in reversed(tr):
        if t<=n-1-K and t>=n-1-RECENCY_BARS: rec=t; break
    if rec is None: return None
    # prev = most recent trough >= MIN_TROUGH_SEP bars before rec
    prev=None
    for t in reversed([x for x in tr if x<rec]):
        if rec-t>=MIN_TROUGH_SEP: prev=t; break
    if prev is None: return None
    h=H.values
    # confirmation: rising run from rec (incl. rec->rec+1) >= CONFIRM_BARS, or crossed >0 after rec (P0-3)
    after=h[rec+1:]
    rising=0
    prevv=h[rec]
    for v in after:
        if v>prevv: rising+=1; prevv=v
        else: break
    confirmed=(rising>=CONFIRM_BARS) or (after>0).any()
    plp,plpd=price_low(df,prev); plr,plrd=price_low(df,rec)
    mom=h[rec]>h[prev]; price_ok=plr<=plp*(1+TOL)
    return dict(prev=prev,rec=rec,h_prev=float(h[prev]),h_rec=float(h[rec]),
                pl_prev=plp,pl_rec=plr,swing_prev=plpd,swing=plrd,
                mom=mom,price_ok=price_ok,confirmed=bool(confirmed),
                diverg=bool(mom and price_ok and confirmed))

def weekly_zone(df,swing_date):
    wk=df.resample("W-FRI").agg(Open=("Open","first"),High=("High","max"),Low=("Low","min"),
                                Close=("Close","last"),Volume=("Volume","sum")).dropna(subset=["Close"])
    last=df.index.max(); buckets=list(wk.index)
    def closed(W): return (W!=buckets[-1]) or (last.weekday()==4)   # P1-9 robust closure
    e={p:ema(wk["Close"],p) for p in WK_EMAS}
    cand=[b for b in buckets if b>=pd.Timestamp(swing_date)]
    if not cand: return dict(status="no_week")
    W=cand[0]
    if not closed(W): return dict(status="pending_week")
    vals={p:float(e[p].loc[W]) for p in WK_EMAS}; lo=min(vals.values()); hi=max(vals.values())
    row=wk.loc[W]
    return dict(status="ok",W=W,emas=vals,band=(lo,hi),
                zone_ok=bool(row["Low"]<=hi and row["High"]>=lo),wlow=float(row["Low"]),whigh=float(row["High"]))

def run_symbol(df):
    H=macd_hist(df["Close"]); rsi=wilder_rsi(df["Close"])
    liq=float((df["Close"]*df["Volume"]).tail(LIQ_WIN).median())
    d=detect(df,H)
    if not d or not d["diverg"]: return dict(flag=0,reason="no_divergence",liq=liq)
    z=weekly_zone(df,d["swing"])
    if z["status"]!="ok": return dict(flag=0,reason=z["status"],liq=liq)
    if not z["zone_ok"]: return dict(flag=0,reason="zone_fail",liq=liq)
    lo=max(0,d["rec"]-K); hi=min(len(rsi)-1,d["rec"]+K); rtv=float(rsi.iloc[lo:hi+1].min())
    a=float(atr(df).iloc[-1])
    if not np.isfinite(a) or a<=0: a=float(df["Close"].iloc[-1])*0.02   # B3: NaN/zero-safe ATR
    return dict(flag=1,reason="FLAGGED",liq=liq,rsi_trough=rtv,
                rsi_check="uncensored" if rtv>=RSI_LB else "censored",
                mom_norm=(d["h_rec"]-d["h_prev"])/a, d=d, z=z,
                below_liq=liq<LIQ_MIN)

# ---------------------------------------------------------------- reporting
def show_bse():
    df,src=fetch("BSE",6); print(f"BSE via {src}: {len(df)} bars {df.index[0].date()}..{df.index[-1].date()}")
    r=run_symbol(df)
    if r["flag"]!=1: print("!! BSE NOT FLAGGED — reason:",r["reason"]); return
    d,z=r["d"],r["z"]
    print("\n===== BSE GOLDEN (production algo, 6y warm-up) =====")
    print(f"Trough_prev  : {df.index[d['prev']].date()}  H={d['h_prev']:+.3f}  priceLow={d['pl_prev']:.2f} @ {pd.Timestamp(d['swing_prev']).date()}")
    print(f"Trough_recent: {df.index[d['rec']].date()}  H={d['h_rec']:+.3f}  priceLow={d['pl_rec']:.2f} @ {pd.Timestamp(d['swing']).date()}")
    print(f"momentum higher-low={d['mom']}  price lower/equal-low={d['price_ok']}  confirmed={d['confirmed']}")
    print(f"WEEKLY W ending {z['W'].date()}: EMA11={z['emas'][11]:.1f} EMA22={z['emas'][22]:.1f} EMA50={z['emas'][50]:.1f}")
    print(f"  band=[{z['band'][0]:.1f},{z['band'][1]:.1f}]  week[L={z['wlow']:.1f},H={z['whigh']:.1f}]  zone_ok={z['zone_ok']}")
    print(f"RSI_trough={r['rsi_trough']:.2f} -> {r['rsi_check']}   liquidity=₹{r['liq']/1e7:.1f}cr/day")

def _sample_eq(n,seed=42):
    import requests,io,csv,random
    S=requests.Session(); S.headers.update({"User-Agent":UA["User-Agent"],"Accept":"text/html"})
    txt=S.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",timeout=20).text
    rows=[{k.strip():(v or "").strip() for k,v in r.items()} for r in csv.DictReader(io.StringIO(txt))]
    eq=[r["SYMBOL"] for r in rows if r.get("SERIES")=="EQ"]
    random.seed(seed); return random.sample(eq,min(n,len(eq)))

def show_basket(nrand=30,large=True,sleep=0.35):
    large_syms=(["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","BHARTIARTL","ITC","LT",
                 "KOTAKBANK","AXISBANK","HINDUNILVR","BAJFINANCE","MARUTI","SUNPHARMA","TITAN",
                 "WIPRO","ONGC","BSE"] if large else [])
    syms=large_syms+_sample_eq(nrand)
    print(f"DRY RUN {len(syms)} symbols ({len(large_syms)} large + {nrand} random EQ) prom_frac={PROM_FRAC}\n")
    ok=failed=insuff=flagged=liq_flagged=illq=badjump=0; t0=time.time()
    for i,s in enumerate(syms,1):
        try:
            df,_=fetch(s,6)
        except Exception as e:
            failed+=1; print(f"[{i:>3}] {s:<12} FAILED {e.__class__.__name__}"); time.sleep(sleep); continue
        if df is None or len(df)<250: insuff+=1; time.sleep(sleep); continue
        ok+=1
        if (df["Close"].pct_change().abs()>0.40).sum()>0: badjump+=1
        r=run_symbol(df)
        liquid=r.get("liq",0)>=LIQ_MIN and float(df["Close"].iloc[-1])>=20
        if not liquid: illq+=1
        if r.get("flag")==1:
            flagged+=1
            if liquid: liq_flagged+=1
            print(f"[{i:>3}] {s:<12} FLAG rsi={r['rsi_check']:<10} liq=₹{r['liq']/1e7:7.1f}cr {'LIQ-OK' if liquid else 'below-liq'}")
        time.sleep(sleep)
    dt=time.time()-t0; N=len(syms); nliq=ok-illq
    print(f"\n--- SUMMARY (prom_frac={PROM_FRAC}) ---")
    print(f"ok={ok} failed={failed} insufficient={insuff} | REAL fail%={failed/max(ok+failed,1)*100:.1f} (excl. insufficient/IPO)")
    print(f"liquid(≥₹5cr,≥₹20)={nliq} | flagged(all fetched)={flagged} ({flagged/max(ok,1)*100:.1f}%) | flagged(liquid only)={liq_flagged} ({liq_flagged/max(nliq,1)*100:.1f}%)")
    print(f"susp-adjust={badjump} | {dt:.0f}s ({dt/N:.1f}s/sym) -> full 2292 ≈ {dt/N*2292/60:.0f} min")

def show_sweep():
    global PROM_FRAC
    df,_=fetch("BSE",6); H=macd_hist(df["Close"]); h=H.values; n=len(df)
    mx=float(np.nanmax(np.abs(h[max(0,n-LOOKBACK):])))
    print(f"BSE prominence sweep (max|H| over 60 = {mx:.2f}); target rec=2026-09-02:")
    saved=PROM_FRAC
    for f in [0.06,0.08,0.10,0.12,0.15,0.20]:
        PROM_FRAC=f; r=run_symbol(df); thr=f*mx
        if r.get("flag")==1:
            d=r["d"]; print(f"  frac={f:.2f} thr={thr:5.2f} -> FLAG   rec={df.index[d['rec']].date()} H_rec={d['h_rec']:+.2f}  zone_ok={r['z']['zone_ok']}")
        else:
            print(f"  frac={f:.2f} thr={thr:5.2f} -> NO-FLAG ({r['reason']})")
    PROM_FRAC=saved

if __name__=="__main__":
    mode=sys.argv[1] if len(sys.argv)>1 else "bse"
    if len(sys.argv)>2 and mode in ("basket","tail"): pass
    if mode=="bse": show_bse()
    elif mode=="sweep": show_sweep()
    elif mode=="tail": show_basket(int(sys.argv[2]) if len(sys.argv)>2 else 200, large=False)
    else: show_basket(int(sys.argv[2]) if len(sys.argv)>2 else 30, large=True)

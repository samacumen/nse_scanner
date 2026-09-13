"""
Golden-test VARIANT MATRIX on BSE Ltd.
Determine which (trough-definition x min-segment x comparison-scope) reproduces
the spec's own bullish-divergence example, so the blueprint's divergence rule is
evidence-based rather than assumed.
"""
import numpy as np, pandas as pd
from golden_test_bse import load, macd_hist, price_low, LOOKBACK_DAYS, TOLERANCE_PCT, K

def neg_run_len(h, i):
    if h[i] >= 0: return 0
    l = i
    while l-1 >= 0 and h[l-1] < 0: l -= 1
    r = i
    while r+1 < len(h) and h[r+1] < 0: r += 1
    return r - l + 1

def strict_troughs(h, min_seg):
    out, i, n = [], 0, len(h)
    while i < n:
        if np.isnan(h[i]) or h[i] >= 0: i += 1; continue
        j = i
        while j < n and h[j] < 0: j += 1
        if (j - i) >= min_seg:
            out.append(min(range(i, j), key=lambda x: h[x]))
        i = j
    return out

def prominence_troughs(h, min_seg, min_prom):
    raw = [i for i in range(1, len(h)-1)
           if not np.isnan(h[i]) and h[i] < 0 and h[i] <= h[i-1] and h[i] < h[i+1]]
    raw = [i for i in raw if neg_run_len(h, i) >= min_seg]
    if min_prom > 0:
        kept = []
        for i in raw:
            l = i
            while l-1 >= 0 and h[l-1] < 0: l -= 1
            r = i
            while r+1 < len(h) and h[r+1] < 0: r += 1
            left_max = max(h[l:i+1]); right_max = max(h[i:r+1])
            prom = min(left_max, right_max) - h[i]
            if prom >= min_prom: kept.append(i)
        raw = kept
    return raw

def diverg(df, H, troughs, scope):
    h = H.values
    recent = [t for t in troughs if t >= len(df) - LOOKBACK_DAYS]
    if len(recent) < 2: return None, "<2 troughs"
    t_rec = recent[-1]
    if scope == "two_most_recent":
        t_prev = recent[-2]
    else:  # recent_vs_deepest_prior
        priors = recent[:-1]
        t_prev = min(priors, key=lambda x: h[x])
    pl_prev, _ = price_low(df, t_prev); pl_rec, _ = price_low(df, t_rec)
    mom = h[t_rec] > h[t_prev]
    price_ok = pl_rec <= pl_prev * (1 + TOLERANCE_PCT)
    ok = mom and price_ok
    tag = (f"{df.index[t_prev].date()}(H{h[t_prev]:+.1f},{pl_prev:.0f}) -> "
           f"{df.index[t_rec].date()}(H{h[t_rec]:+.1f},{pl_rec:.0f})")
    return ok, tag

def main():
    df, src = load()
    _, _, H = macd_hist(df["Close"]); h = H.values
    print(f"source={src} bars={len(df)}\n")
    header = f"{'trough-def':<26}{'minSeg':<7}{'scope':<22}{'DIVERG':<8}pair"
    print(header); print("-"*len(header))
    defs = [("strict", lambda ms: strict_troughs(h, ms)),
            ("prominence(prom=0)", lambda ms: prominence_troughs(h, ms, 0)),
            ("prominence(prom=3)", lambda ms: prominence_troughs(h, ms, 3.0))]
    for dname, dfn in defs:
        for ms in (1, 2):
            tr = dfn(ms)
            for scope in ("two_most_recent", "recent_vs_deepest_prior"):
                ok, tag = diverg(df, H, tr, scope)
                print(f"{dname:<26}{ms:<7}{scope:<22}{str(ok):<8}{tag}")
    print("\n(Target: the config must yield DIVERG=True to reproduce the spec's BSE example.)")

if __name__ == "__main__":
    main()

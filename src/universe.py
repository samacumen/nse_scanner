"""NSE universe (blueprint 7 step 2).

Download EQUITY_L.csv (browser UA; NSE session priming fallback), strip the
leading-space headers, filter by series, build (symbol, isin, name). Optional
index_filter pre-trim. Track identity by ISIN + weekly diff (renames/adds/drops).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pandas as pd
import requests

# Fixed in code (blueprint 6): NSE URLs.
EQUITY_L_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_HOME = "https://www.nseindia.com"
INDEX_CSV = {
    "NIFTY500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "SMALLCAP250": "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
}
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"})
    return s


def _get_text(url: str, session: requests.Session, prime: bool = False) -> str:
    if prime:
        try:
            session.get(NSE_HOME, timeout=20)
        except Exception:
            pass
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return r.text


def download_equity_list(session: requests.Session | None = None) -> pd.DataFrame:
    """Return the raw EQUITY_L.csv as a DataFrame with STRIPPED headers/values."""
    s = session or _session()
    txt = _get_text(EQUITY_L_URL, s)
    if "SYMBOL" not in txt.split("\n", 1)[0].upper():
        # Non-CSV (WAF/HTML) -> prime an NSE session then retry.
        txt = _get_text(EQUITY_L_URL, s, prime=True)
    rows = [
        {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        for r in csv.DictReader(io.StringIO(txt))
    ]
    return pd.DataFrame(rows)


def _index_members(token: str, session: requests.Session) -> set:
    members: set = set()
    for part in token.split("+"):
        part = part.strip().upper()
        if part not in INDEX_CSV:
            raise ValueError(
                f"unknown index_filter {part!r}; known: {sorted(INDEX_CSV)} (join with '+')"
            )
        txt = _get_text(INDEX_CSV[part], session, prime=True)
        for row in csv.DictReader(io.StringIO(txt)):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            sym = row.get("Symbol") or row.get("SYMBOL")
            if sym:
                members.add(sym.strip().upper())
    return members


def build_universe(cfg, session: requests.Session | None = None) -> pd.DataFrame:
    """Return DataFrame [symbol, isin, name, series] filtered per config.

    symbols_override short-circuits index/series/max filters but still resolves
    isin/name from EQUITY_L when possible.
    """
    s = session or _session()
    raw = download_equity_list(s)

    def col(df, *names):
        for n in names:
            if n in df.columns:
                return n
        raise KeyError(f"EQUITY_L missing any of {names}; got {list(df.columns)}")

    c_sym = col(raw, "SYMBOL")
    c_name = col(raw, "NAME OF COMPANY", "NAME_OF_COMPANY")
    c_series = col(raw, "SERIES")
    c_isin = col(raw, "ISIN NUMBER", "ISIN_NUMBER", "ISIN")

    df = pd.DataFrame({
        "symbol": raw[c_sym].str.strip(),
        "name": raw[c_name].str.strip(),
        "series": raw[c_series].str.strip(),
        "isin": raw[c_isin].str.strip(),
    })

    if cfg.universe.symbols_override:
        want = [x.strip().upper() for x in cfg.universe.symbols_override]
        sub = df[df["symbol"].str.upper().isin(want)].copy()
        found = set(sub["symbol"].str.upper())
        for sym in want:
            if sym not in found:  # unlisted testing symbol -> synth row, still fetchable
                sub = pd.concat([sub, pd.DataFrame([{
                    "symbol": sym, "name": sym, "series": "EQ", "isin": ""}])],
                    ignore_index=True)
        return sub.reset_index(drop=True)

    df = df[df["series"].isin(cfg.universe.series)].copy()

    if cfg.universe.index_filter:
        members = _index_members(cfg.universe.index_filter, s)
        df = df[df["symbol"].str.upper().isin(members)].copy()

    df = df.drop_duplicates(subset=["symbol"]).reset_index(drop=True)
    if cfg.universe.max_symbols:
        df = df.head(cfg.universe.max_symbols).reset_index(drop=True)
    return df


def diff_universe(prev: pd.DataFrame, cur: pd.DataFrame) -> dict:
    """ISIN-keyed diff: renames (same ISIN, changed symbol), adds, drops."""
    result = {"renamed": [], "added": [], "dropped": []}
    if prev is None or prev.empty:
        return result
    prev_valid = prev[prev["isin"].astype(str) != ""]
    cur_valid = cur[cur["isin"].astype(str) != ""]
    p = dict(zip(prev_valid["isin"], prev_valid["symbol"]))
    c = dict(zip(cur_valid["isin"], cur_valid["symbol"]))
    for isin, sym in c.items():
        if isin not in p:
            result["added"].append(sym)
        elif p[isin] != sym:
            result["renamed"].append((p[isin], sym, isin))
    for isin, sym in p.items():
        if isin not in c:
            result["dropped"].append(sym)
    return result


def save_snapshot(df: pd.DataFrame, universe_dir: Path) -> pd.DataFrame | None:
    """Persist current EQUITY_L snapshot; return the previous one (for diffing)."""
    universe_dir.mkdir(parents=True, exist_ok=True)
    cur_path = universe_dir / "EQUITY_L.csv"
    prev_path = universe_dir / "EQUITY_L_prev.csv"
    prev = None
    if cur_path.exists():
        try:
            prev = pd.read_csv(cur_path, dtype=str).fillna("")
        except Exception:
            prev = None
        cur_path.replace(prev_path)
    df.to_csv(cur_path, index=False)
    return prev

"""Trader goldens (feedback on the v1.2 report -> Rule Spec v1.3) - offline, frozen 2026-09-25 data
(the data behind the 2026-09-27 report; JKBANK_2026-09-25.parquet is J&KBANK's file).

  J&KBANK: with the 1-day trough rule 17 Aug is a trough (under +-3 it was not: 12 Aug was lower),
           so the pair is 17 Aug -> 2 Sep (v1.2 compared 31 Jul -> 2 Sep) - and it passes.
  NH: the pair stays 10 Aug -> 17 Sep and passes momentum + price, but the fall bottomed at
      1781.00 on 19 Aug, between the dips and below both lows: the v1.3 no-intervening-breach
      rule fails it (the trader's "lower low not satisfied").
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.config import load_config
from src import store as storemod
from src import indicators as ind
from src.divergence import detect_divergence
import run_scanner


def _load(name):
    df, _ = storemod.load_parquet(ROOT / "tests" / "fixtures" / f"{name}_2026-09-25.parquet")
    assert df.index.max().date().isoformat() == "2026-09-25"
    return df


def _div(df, cfg):
    return detect_divergence(df, ind.macd_hist(df["Close"], cfg.macd.fast, cfg.macd.slow, cfg.macd.signal), cfg)


def _dates(div):
    return div.prev_date.date().isoformat(), div.recent_date.date().isoformat()


def test_jkbank_compares_17_aug_with_2_sep_and_passes():
    cfg = load_config()
    df = _load("JKBANK")
    div = _div(df, cfg)
    assert _dates(div) == ("2026-08-17", "2026-09-02")
    assert abs(div.h_prev - (-1.3978)) < 0.0005 and abs(div.h_recent - (-0.0858)) < 0.0005
    assert abs(div.pl_prev - 147.13) < 0.005 and abs(div.pl_recent - 144.00) < 0.005
    assert abs(div.between_low - 146.00) < 0.005 and div.between_low_date.date().isoformat() == "2026-08-24"
    assert div.is_true
    kind, rec = run_scanner.analyze_symbol("J&KBANK", df, "", "J&K Bank", cfg)
    assert kind == "flagged" and rec["week_start"].date().isoformat() == "2026-08-31"
    cfg.divergence.trough_pivot_k = 3  # v1.2's +-3 rule: 17 Aug is not a trough
    assert _dates(_div(df, cfg)) == ("2026-07-31", "2026-09-02")


def test_nh_fails_on_the_19_aug_low_between_its_dips():
    cfg = load_config()
    df = _load("NH")
    div = _div(df, cfg)
    assert _dates(div) == ("2026-08-10", "2026-09-17")
    assert div.momentum_ok and div.price_ok  # what v1.2 checked (NH was ranked #8)
    assert abs(div.pl_prev - 1819.40) < 0.005 and abs(div.pl_recent - 1811.00) < 0.005
    assert abs(div.between_low - 1781.00) < 0.005 and div.between_low_date.date().isoformat() == "2026-08-19"
    assert not div.no_breach_ok and not div.is_true and div.reason == "intervening_breach"
    kind, reason = run_scanner.analyze_symbol("NH", df, "", "NH", cfg)
    assert (kind, reason) == ("skip", "no_divergence:intervening_breach")

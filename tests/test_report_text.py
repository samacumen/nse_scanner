"""Report prose tells the truth, and the new report parts render - offline.

Built from the real BSE record (frozen fixture), whose swing low 3131.50 sits BELOW
the weekly band floor 3178.3 (the week's range still touches the band):
  - the narrative never claims the low itself fell inside the band (spec 3.2 tests
    the week's range) and prints the SWING-LOW date for the low, not the trough date;
  - the liquidity line never says "above the minimum" for a stock below it;
  - a spec pass that fails liquidity is returned as 'illiquid_pass' and listed with
    what it fell short on; the as-of line says how many stocks end on that date.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.config import load_config
from src import store as storemod
from src import rank as rankmod
from src import report as reportmod
import run_scanner

FIXTURE = ROOT / "tests" / "fixtures" / "BSE_2026-09-22.parquet"
META = {"date": "2026-09-22", "generated": "test", "U": 1594, "L": 1, "F": 1, "P": 0,
        "as_of_n": 1591, "listed": 2319, "skipped_insufficient": 0,
        "illiquid_pass": [{"symbol": "AAA", "liquidity": 1.2e7, "last_close": 50.0},
                          {"symbol": "BBB", "liquidity": 9.0e7, "last_close": 12.5}]}


def _bse(cfg):
    df, _ = storemod.load_parquet(FIXTURE)
    kind, rec = run_scanner.analyze_symbol("BSE", df, "", "BSE Ltd", cfg)
    assert kind == "flagged"
    return df, rec


def _what_happened(text):
    return text.split("What happened:")[1].split("The checks it passed:")[0]


def test_narrative_uses_swing_date_and_never_says_the_low_was_inside():
    cfg = load_config()
    _, rec = _bse(cfg)
    assert rec["pl_recent"] < rec["band_lo"]  # the low itself is below the band
    rec["swing_recent_date"] = pd.Timestamp("2026-09-01")  # make it differ from the trough date
    text = reportmod.build_report_text(rankmod.rank([rec], cfg), [], META, cfg)
    para = " ".join(_what_happened(text).split())
    assert "down to 3131.50 on 2026-09-01)" in para
    assert "2026-09-02" not in para
    assert "fell inside" not in text
    assert "That week's price range touched BSE's weekly EMA 11/22/50 support band" in para


def test_liquidity_line_is_truthful_when_the_filter_is_off():
    cfg = load_config()
    cfg.liquidity.apply_as_filter = False
    cfg.liquidity.min_median_traded_value_inr = 1e12  # BSE is now below the floor
    _, rec = _bse(cfg)
    text = reportmod.build_report_text(rankmod.rank([rec], cfg), [], META, cfg)
    assert "above the Rs" not in text
    assert "below the Rs 100000 cr/day minimum" in text


def test_illiquid_spec_pass_is_listed_with_its_reason():
    cfg = load_config()
    cfg.liquidity.min_median_traded_value_inr = 1e12
    df, _ = storemod.load_parquet(FIXTURE)
    kind, info = run_scanner.analyze_symbol("BSE", df, "", "BSE Ltd", cfg)
    assert kind == "illiquid_pass" and info["symbol"] == "BSE"
    text = reportmod.build_report_text([], [], META, load_config())  # default floors: Rs 5 cr, Rs 20
    assert "PASSES THE SETUP BUT FAILS LIQUIDITY - 2" in text
    assert "AAA (Rs 1.20 cr/d)" in text and "BBB (price Rs 12.50)" in text
    assert "latest bar for 1591 of 1594 scanned stocks" in text


def test_rsi_band_and_missing_turnover_are_printed_truthfully():
    cfg = load_config()
    cfg.rsi.lower_band = 35.0  # BSE's RSI trough 33.29 is now below the band
    _, rec = _bse(cfg)
    meta = dict(META, illiquid_pass=[{"symbol": "NOVOL", "liquidity": float("nan"), "last_close": 50.0}])
    text = reportmod.build_report_text(rankmod.rank([rec], cfg), [], meta, cfg)
    assert "RSI dipped below 35" in text and "below 30" not in text and "above 30" not in text
    assert "NOVOL (turnover n/a)" in text

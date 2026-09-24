"""TRUTHFULNESS test (blueprint 8.7 / 11).

Builds the BSE record through the real pipeline, renders the report, then
parses the printed text back and asserts every printed number EQUALS the
computed value (at the printed precision) - the report contains zero
hardcoded/placeholder data. Also asserts the listed stock genuinely passed
8.2 (divergence) AND 8.3 (zone).

Offline: uses the frozen BSE fixture (tests/fixtures/BSE_2026-09-22.parquet).
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.config import load_config
from src import store as storemod
from src import rank as rankmod
from src import report as reportmod
import run_scanner


@pytest.fixture(scope="module")
def bse_report():
    cfg = load_config()
    df, _meta = storemod.load_parquet(ROOT / "tests" / "fixtures" / "BSE_2026-09-22.parquet")
    kind, rec = run_scanner.analyze_symbol("BSE", df, "INE118H01025", "BSE Ltd", cfg)
    assert kind == "flagged"
    ranked = rankmod.rank([rec], cfg)
    meta = {"date": df.index.max().date().isoformat(), "generated": "test",
            "U": 1, "L": 1, "F": 1, "P": 0}
    text = reportmod.build_report_text(ranked, [], meta, cfg)
    return cfg, ranked[0], text


def _f(pattern, text):
    m = re.search(pattern, text)
    assert m, f"pattern not found: {pattern}"
    return float(m.group(1))


def test_printed_equals_computed(bse_report):
    cfg, r, text = bse_report
    # Divergence line numbers.
    assert re.search(r"dip on 2026-08-21", text)
    assert re.search(r"higher-momentum dip on 2026-09-02", text)
    h_prev = _f(r"dip on [\d-]+ \(MACD ([+-]?\d+\.\d+)", text)
    pl_prev = _f(r"dip on [\d-]+ \(MACD [+-]?\d+\.\d+, low (\d+\.\d+)", text)
    h_rec = _f(r"higher-momentum dip on [\d-]+ \(MACD ([+-]?\d+\.\d+)", text)
    pl_rec = _f(r"higher-momentum dip on [\d-]+ \(MACD [+-]?\d+\.\d+, low (\d+\.\d+)", text)
    assert h_prev == round(r["h_prev"], 2)
    assert pl_prev == round(r["pl_prev"], 2)
    assert h_rec == round(r["h_recent"], 2)
    assert pl_rec == round(r["pl_recent"], 2)

    # Weekly band + range.
    band_lo = _f(r"band (\d+\.\d+) to \d+\.\d+;", text)
    band_hi = _f(r"band \d+\.\d+ to (\d+\.\d+);", text)
    assert band_lo == round(r["band_lo"], 1)
    assert band_hi == round(r["band_hi"], 1)

    # RSI + liquidity.
    rsi = _f(r"lowest RSI within \d+ days of the MACD dip was (\d+\.\d+)", text)
    assert rsi == round(r["rsi_trough"], 2)
    liq_cr = _f(r"about Rs (\d+) cr traded per day", text)
    assert liq_cr == round(r["liquidity"] / 1e7)


def test_listed_stock_passed_8_2_and_8_3(bse_report):
    cfg, r, text = bse_report
    assert r["momentum_ok"] and r["price_ok"]                      # 8.2 (spec 2)
    assert r["zone_ok"] is True                                    # 8.3
    assert "uncensored" in text
    assert r["rsi_check"] == "uncensored"


def test_golden_values_present(bse_report):
    cfg, r, text = bse_report
    assert "-18.13" in text
    assert "3131.50" in text
    assert "2026-08-31" in text  # Zone_week_date = start of the weekly EMA-zone candle
    assert "3178.3 to 3520.1" in text
    assert "33.29" in text

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
def _meta(rec, *ill):
    """Report meta whose illiquid spec passes are full copies of `rec` with the given overrides."""
    return {"date": "2026-09-22", "generated": "test", "U": 1594, "L": 1, "F": 1, "P": 0,
            "as_of_n": 1591, "listed": 2319, "skipped_insufficient": 0,
            "illiquid_pass": [dict(rec, **o) for o in ill]}


AAA = {"symbol": "AAA", "liquidity": 1.2e7, "last_close": 50.0}
BBB = {"symbol": "BBB", "liquidity": 9.0e7, "last_close": 12.5}


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
    text = reportmod.build_report_text(rankmod.rank([rec], cfg), [], _meta(rec, AAA), cfg)
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
    text = reportmod.build_report_text(rankmod.rank([rec], cfg), [], _meta(rec), cfg)
    assert "above the Rs" not in text
    assert "below the Rs 100000 cr/day minimum" in text


def test_illiquid_spec_pass_is_listed_with_its_reason():
    cfg = load_config()
    cfg.liquidity.min_median_traded_value_inr = 1e12
    df, _ = storemod.load_parquet(FIXTURE)
    kind, info = run_scanner.analyze_symbol("BSE", df, "", "BSE Ltd", cfg)
    assert kind == "illiquid_pass" and info["symbol"] == "BSE"
    assert info["rsi_check"] == "uncensored" and abs(info["rsi_trough"] - 33.34) < 0.01  # spec 4 on it too
    text = reportmod.build_report_text([], [], _meta(info, AAA, BBB), load_config())  # floors Rs 5 cr / Rs 20
    s5 = text.split("SECTION 5 - THINLY TRADED SETUPS (2, not ranked)")[1]
    row = lambda sym: [ln for ln in s5.splitlines() if ln.split()[:1] == [sym]][0]
    assert "turnover " in row("AAA") and row("AAA").rstrip().endswith("1.20")   # short of turnover; its value
    assert "price Rs 12.50" in row("BBB") and "turnover" not in row("BBB")
    assert "latest bar for 1591 of 1594 scanned stocks" in text


def test_rsi_band_and_missing_turnover_are_printed_truthfully():
    cfg = load_config()
    cfg.rsi.lower_band = 35.0  # BSE's RSI trough 33.29 is now below the band
    _, rec = _bse(cfg)
    meta = _meta(rec, {"symbol": "NOVOL", "liquidity": float("nan"), "last_close": 50.0})
    text = reportmod.build_report_text(rankmod.rank([rec], cfg), [], meta, cfg)
    assert "RSI dipped below 35" in text and "below 30" not in text and "above 30" not in text
    assert "NOVOL" in text and "turnover n/a" in text.split("SECTION 5")[1]


def test_thin_setups_carry_every_spec5_field_and_all_flags_are_counted():
    cfg = load_config()
    _, rec = _bse(cfg)
    ill = dict(rec, symbol="AAA", liquidity=1.2e7, last_date=pd.Timestamp("2026-09-18"))
    text = reportmod.build_report_text(rankmod.rank([rec], cfg), [], _meta(rec, ill), cfg)
    assert "2 stocks pass the setup (the spec's flag):" in text
    assert "1 tradeable and ranked" in text and "1 thinly traded" in text
    lines = text.split("SECTION 5")[1].splitlines()
    i = [n for n, ln in enumerate(lines) if ln.split()[:1] == ["AAA"]][0]
    glance, detail = lines[i], lines[i + 1]
    for field in ("2026-08-21", "2026-09-02", "2026-08-31", "33.34 uncensored", "1.20", "(data to 2026-09-18)"):
        assert field in glance, field
    for field in ("MACD -18.15 -> -3.49", "LOW 3223.00 @ 2026-08-21 -> 3131.50 @ 2026-09-02",
                  "WEEK 3131.5 to 3474.0", "EMA11/22/50 3520.1 / 3498.0 / 3178.3"):
        assert field in detail, field
    assert "The latest bar is" in text and "2026-09-22 for 1591 of 1594 scanned stocks" in text


def test_glance_first_layout_lists_every_flag_once():
    cfg = load_config()
    _, rec = _bse(cfg)
    many = [dict(rec, symbol=f"S{i:02d}", h_recent=rec["h_recent"] + i * 0.01) for i in range(12)]
    ranked = rankmod.rank(many, cfg)
    text = reportmod.build_report_text(ranked, ["WAIT1 (data to 2026-09-18)"], _meta(rec, AAA), cfg)
    heads = ["AT A GLANCE", "HOW TO READ", "SECTION 1 - TOP 10", "SECTION 2 - WHY THE TOP 10",
             "SECTION 3 - OTHER TRADEABLE SETUPS (#11-#12)", "SECTION 4 - WAITING", "SECTION 5 - THINLY",
             "SCAN SUMMARY", "SETTINGS USED", "NOTES"]
    pos = [text.find(h) for h in heads[:7] + heads[8:]]
    assert all(p >= 0 for p in pos) and pos == sorted(pos)
    s2 = text.split("SECTION 2")[1].split("SECTION 3")[0]
    assert s2.count("What happened:") == 10  # plain words for the top 10 only
    glance = [ln.split()[1] for ln in text.splitlines() if ln[:7].strip().isdigit() and ln.split()[1].startswith("S")]
    assert sorted(glance) == sorted(r["symbol"] for r in ranked)  # each ranked flag once (Sections 1 + 3)
    s3 = text.split("SECTION 3")[1].split("SECTION 4")[0]
    assert s3.count("MACD ") == 2 and " > " not in s3  # a detail line per stock; arrows, not "greater than"
    assert "WAIT1 (data to 2026-09-18)" in text


def test_csv_holds_every_spec_flag_marking_the_unranked():
    cfg = load_config()
    _, rec = _bse(cfg)
    ranked = rankmod.rank([rec], cfg)
    df = reportmod._flagged_dataframe(ranked, [dict(rec, symbol="AAA", liquidity=1.2e7)])
    assert list(df["symbol"]) == ["BSE", "AAA"] and list(df["ranked"]) == [True, False]
    assert pd.isna(df.loc[1, "rank"]) and df.loc[1, "RSI_check"] == "uncensored"


def test_small_values_every_liquid_flag_ranked_and_csv_ranks():
    assert reportmod._h(-0.00034) == "-0.0003" and reportmod._h(-18.127) == "-18.13"
    assert reportmod._lvl(2.2134) == "2.213" and reportmod._lvl(21.5) == "21.50" and reportmod._lvl(3178.26) == "3178.3"
    cfg = load_config()
    assert not hasattr(cfg.ranking, "min_score")  # removed: no score floor can hide a spec flag
    _, rec = _bse(cfg)
    ranked = rankmod.rank([rec, dict(rec, symbol="CCC")], cfg)
    assert [r["rank"] for r in ranked] == [1, 2]
    text = reportmod.build_report_text(ranked, [], dict(_meta(rec), F=2), cfg)
    assert "2 stocks pass the setup (the spec's flag):" in text and "2 tradeable and ranked" in text
    assert "lowest RSI within 3 trading days of the MACD dip" in text
    df = reportmod._flagged_dataframe(rankmod.rank([dict(rec)], load_config()), [dict(rec, symbol="AAA")])
    assert str(df["rank"].dtype) == "Int64" and df["rank"].tolist()[0] == 1


def test_windows_notepad_bom_config_loads(tmp_path):
    cfg_file = tmp_path / "config.txt"
    cfg_file.write_bytes(b"\xef\xbb\xbf[ranking]\ntop_n = 7\n")  # "UTF-8 with BOM", as Notepad can save it
    cfg = load_config(cfg_file)
    assert cfg.ranking.top_n == 7 and cfg.output.write_full_flagged_csv is False  # blank/absent -> no CSV


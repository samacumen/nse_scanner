"""Closed bars only (spec 7.5) - offline, on the frozen BSE fixture.

  1) Step 1 never stores a still-forming daily candle (downloaded before its 15:30 IST close);
  2) the last weekly candle counts as closed once the data was downloaded at/after that
     week's Friday 15:30 IST close - also when Friday is an exchange holiday (Good Friday
     2026-04-03: Thursday 2026-04-02 is the week's last bar) - and never before it.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src import store as storemod
from src.zone import weekly_zone

FIXTURE = ROOT / "tests" / "fixtures" / "BSE_2026-09-22.parquet"


def _utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_forming_daily_bar_is_dropped_before_the_close():
    df, _ = storemod.load_parquet(FIXTURE)  # last bar Tue 2026-09-22
    before = storemod.drop_forming_bar(df, _utc("2026-09-22T09:59:00"))   # 15:29 IST
    at_close = storemod.drop_forming_bar(df, _utc("2026-09-22T10:00:00"))  # 15:30 IST
    next_morning = storemod.drop_forming_bar(df, _utc("2026-09-23T02:00:00"))
    assert before.index[-1].date().isoformat() == "2026-09-21"
    assert at_close.index[-1].date().isoformat() == "2026-09-22"
    assert len(next_morning) == len(df)


def test_friday_holiday_week_closes_at_friday_1530_ist():
    cfg = load_config()
    df, _ = storemod.load_parquet(FIXTURE)
    cut = df.loc[:"2026-04-02"]
    assert cut.index[-1].date().isoformat() == "2026-04-02"
    swing = pd.Timestamp("2026-04-02")
    before = weekly_zone(cut, swing, cfg, _utc("2026-04-03T09:59:00"))  # Fri 15:29 IST
    after = weekly_zone(cut, swing, cfg, _utc("2026-04-03T10:00:00"))   # Fri 15:30 IST
    assert before.status == "pending_week"
    assert after.status == "ok" and after.W.date().isoformat() == "2026-04-03"


def test_friday_partial_week_is_not_closed_before_the_close():
    cfg = load_config()
    df, _ = storemod.load_parquet(FIXTURE)
    cut = df.loc[:"2026-09-04"]  # data ends on a Friday bar
    swing = pd.Timestamp("2026-09-02")
    assert weekly_zone(cut, swing, cfg, _utc("2026-09-04T06:00:00")).status == "pending_week"  # 11:30 IST
    assert weekly_zone(cut, swing, cfg, _utc("2026-09-04T12:00:00")).status == "ok"            # 17:30 IST


def test_without_download_time_the_week_needs_its_friday_bar():
    cfg = load_config()
    df, _ = storemod.load_parquet(FIXTURE)
    assert weekly_zone(df.loc[:"2026-04-02"], pd.Timestamp("2026-04-02"), cfg).status == "pending_week"
    assert weekly_zone(df.loc[:"2026-09-04"], pd.Timestamp("2026-09-02"), cfg).status == "ok"
    assert storemod.parse_fetched_at("nan") is None and storemod.parse_fetched_at("") is None

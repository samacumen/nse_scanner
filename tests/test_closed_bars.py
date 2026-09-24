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


def test_a_stock_lagging_the_cohort_keeps_its_last_week_pending():
    cfg = load_config()
    df, _ = storemod.load_parquet(FIXTURE)
    cut = df.loc[:"2026-09-03"]  # Yahoo gave this stock only Mon-Thu of the week ending 2026-09-04
    after_close = _utc("2026-09-04T12:00:00")  # Fri 17:30 IST
    swing = pd.Timestamp("2026-09-02")
    assert weekly_zone(cut, swing, cfg, after_close).status == "ok"  # clock alone would close it
    lagging = {"cohort_newest": pd.Timestamp("2026-09-04"), "incomplete_week": None}
    assert weekly_zone(cut, swing, cfg, after_close, lagging).status == "pending_week"
    nse_says = {"cohort_newest": pd.Timestamp("2026-09-03"), "incomplete_week": pd.Timestamp("2026-09-04")}
    assert weekly_zone(cut, swing, cfg, after_close, nse_says).status == "pending_week"
    holiday = {"cohort_newest": pd.Timestamp("2026-09-03"), "incomplete_week": None}
    assert weekly_zone(cut, swing, cfg, after_close, holiday).status == "ok"


def test_last_week_check_asks_nse_only_when_the_week_looks_over():
    calls = []
    def held(answer, probe=True):
        def fn(day, now):  # NSE: the newest bar's day is a session (probe); later days -> answer
            calls.append(day.date().isoformat())
            return probe if day.date().isoformat() == "2026-04-02" else answer
        return fn
    sat = _utc("2026-04-04T04:00:00")
    assert storemod.last_week_check("2026-04-02", _utc("2026-04-03T09:00:00"), held(True))["sessions_missing"] == []
    assert calls == []  # before Friday 15:30 IST: not asked
    assert storemod.last_week_check("2026-04-02", sat, held(False)) == {
        "week": "2026-04-03", "cohort_newest": "2026-04-02", "checked_at": "2026-04-04T04:00:00Z",
        "sessions_missing": [], "unknown": []}  # Good Friday: no session -> the week is complete
    assert storemod.last_week_check("2026-04-02", sat, held(True))["sessions_missing"] == ["2026-04-03"]
    assert storemod.last_week_check("2026-04-02", sat, held(None))["unknown"] == ["2026-04-03"]
    assert storemod.last_week_check("2026-04-03", sat, held(True))["sessions_missing"] == []  # has Friday
    # probe fails (NSE unreachable or its file names changed) -> every later day is unknown
    assert storemod.last_week_check("2026-04-02", sat, held(False, probe=None))["unknown"] == ["2026-04-03"]


def test_nse_status_codes_and_the_week_guard_file(tmp_path):
    from src.universe import session_from_status
    fri = pd.Timestamp("2026-04-03")
    assert session_from_status(200, fri, fri.date()) is True
    assert session_from_status(404, fri, pd.Timestamp("2026-04-04").date()) is False
    assert session_from_status(404, fri, fri.date()) is None   # same day: NSE may not have published
    assert session_from_status(503, fri, pd.Timestamp("2026-04-04").date()) is None
    man = pd.DataFrame({"last_date": ["2026-09-03", "2026-09-04", ""]})
    f = tmp_path / "week_check.json"
    f.write_text('{"week": "2026-09-04", "cohort_newest": "2026-09-04", "sessions_missing": ["2026-09-04"], "unknown": []}')
    guard, note = storemod.load_week_guard(man, f)
    assert guard["cohort_newest"] == pd.Timestamp("2026-09-04")
    assert guard["incomplete_week"] == pd.Timestamp("2026-09-04") and "stays PENDING" in note
    f.write_text('{"week": "2026-09-04", "cohort_newest": "2026-09-04", "sessions_missing": [], "unknown": ["2026-09-04"]}')
    guard, note = storemod.load_week_guard(man, f)
    assert guard["incomplete_week"] is None and "unavailable" in note
    f.write_text('{"week": "2026-08-28", "cohort_newest": "2026-08-27", "sessions_missing": ["2026-08-28"]}')
    guard, note = storemod.load_week_guard(man, f)  # stale: from an older (interrupted) download
    assert guard["incomplete_week"] is None and note == ""
    f.write_text('{"week": ')  # corrupt: never crashes Step 2
    guard, note = storemod.load_week_guard(man, f)
    assert guard["incomplete_week"] is None and "unreadable" in note


def test_cache_is_not_reused_across_a_session_close():
    closed = storemod.session_closed_between
    assert closed(_utc("2026-09-24T04:30:00"), _utc("2026-09-24T10:30:00"))       # Thu 10:00 -> 16:00 IST
    assert not closed(_utc("2026-09-24T10:30:00"), _utc("2026-09-24T14:30:00"))   # Thu 16:00 -> 20:00 IST
    assert not closed(_utc("2026-09-25T10:30:00"), _utc("2026-09-26T04:30:00"))   # Fri 16:00 -> Sat 10:00
    assert closed(_utc("2026-09-25T04:30:00"), _utc("2026-09-26T03:30:00"))       # Fri 10:00 -> Sat 09:00
    assert not closed(_utc("2026-09-26T04:30:00"), _utc("2026-09-27T10:30:00"))   # weekend


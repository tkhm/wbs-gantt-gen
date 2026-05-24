"""Business-day calendar tests."""

from __future__ import annotations

from datetime import date

from wbsgen.bizcal import WorkdayCalendar
from wbsgen.model import CalendarConfig


def test_index_to_date_skips_weekend():
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig())
    assert cal.to_date(0) == date(2026, 6, 1)  # Mon
    assert cal.to_date(4) == date(2026, 6, 5)  # Fri
    assert cal.to_date(5) == date(2026, 6, 8)  # Mon (skip weekend)


def test_round_trip():
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig())
    for i in range(20):
        d = cal.to_date(i)
        assert cal.to_index(d) == i


def test_snap_to_working_day():
    # 2026-06-06 is a Saturday; calendar should snap forward to Monday.
    cal = WorkdayCalendar(date(2026, 6, 6), CalendarConfig())
    assert cal.start == date(2026, 6, 8)


def test_jp_holidays_preset_skipped():
    # 2026-07-20 is "海の日" (Marine Day). With preset=jp it should be skipped.
    cfg = CalendarConfig(
        working_days=["mon", "tue", "wed", "thu", "fri"],
        holidays_preset="jp",
    )
    cal = WorkdayCalendar(date(2026, 7, 13), cfg)
    # 2026-07-13 (Mon), 14 (Tue), 15 (Wed), 16 (Thu), 17 (Fri), then 20 (Mon, holiday)
    # so index 5 should be 2026-07-21 (Tue), not 2026-07-20.
    assert cal.to_date(5) == date(2026, 7, 21)


def test_custom_holiday():
    cfg = CalendarConfig(
        working_days=["mon", "tue", "wed", "thu", "fri"],
        holidays=[date(2026, 6, 3)],
    )
    cal = WorkdayCalendar(date(2026, 6, 1), cfg)
    # 2026-06-01 (Mon)=0, 02 (Tue)=1, then 03 (Wed) is holiday, skip to 04 (Thu)
    assert cal.to_date(2) == date(2026, 6, 4)

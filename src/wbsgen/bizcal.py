"""Business-day calendar.

Bidirectional projection between integer work-day index (0-based) and
calendar dates. The scheduler stays integer-only; this module handles
all date arithmetic.

Examples
--------
>>> from datetime import date
>>> cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig())
>>> cal.to_date(0)
datetime.date(2026, 6, 1)
>>> cal.to_date(5)  # skips the weekend
datetime.date(2026, 6, 8)
>>> cal.to_index(date(2026, 6, 8))
5
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from wbsgen.model import CalendarConfig

_WEEKDAY_MAP = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


class WorkdayCalendar:
    """Map work-day indices to calendar dates and back.

    The calendar's "day 0" is the project's start date (or the next
    working day after it if start falls on a non-working day).
    """

    def __init__(self, start: date, config: CalendarConfig):
        self.config = config
        self.working_weekdays: set[int] = {
            _WEEKDAY_MAP[d.lower()] for d in config.working_days
        }
        self.holidays: set[date] = set(config.holidays)
        if config.holidays_preset == "jp":
            self._jp_holidays_loaded = False  # lazy expand around requested range
        else:
            self._jp_holidays_loaded = True  # nothing to add
        self._start_raw = start
        self.start: date = self._snap_to_working_day(start)

        # Cache: index -> date and date -> index
        self._index_to_date: list[date] = [self.start]
        self._date_to_index: dict[date, int] = {self.start: 0}

    def _is_working_day(self, d: date) -> bool:
        if d.weekday() not in self.working_weekdays:
            return False
        self._ensure_jp_holidays(d)
        return d not in self.holidays

    def _snap_to_working_day(self, d: date) -> date:
        # Pre-expand holidays once to cover the snap.
        self._ensure_jp_holidays(d)
        cur = d
        for _ in range(366):
            if cur.weekday() in self.working_weekdays and cur not in self.holidays:
                return cur
            cur += timedelta(days=1)
        raise RuntimeError(
            f"could not find a working day within 366 days of {d}"
        )

    def _ensure_jp_holidays(self, around: date) -> None:
        if self._jp_holidays_loaded:
            return
        # Lazy load: expand all JP holidays from start year to start year + 10.
        try:
            import jpholiday  # type: ignore
        except ImportError:
            self._jp_holidays_loaded = True
            return
        y0 = min(self._start_raw.year, around.year) - 1
        y1 = max(self._start_raw.year, around.year) + 10
        for y in range(y0, y1 + 1):
            for d, _name in jpholiday.year_holidays(y):
                self.holidays.add(d)
        self._jp_holidays_loaded = True

    def _extend_to(self, target_index: int) -> None:
        """Ensure the index→date cache covers `target_index`."""
        while len(self._index_to_date) <= target_index:
            last = self._index_to_date[-1]
            nxt = last + timedelta(days=1)
            while not self._is_working_day(nxt):
                nxt += timedelta(days=1)
            self._index_to_date.append(nxt)
            self._date_to_index[nxt] = len(self._index_to_date) - 1

    def to_date(self, index: int) -> date:
        if index < 0:
            raise ValueError(f"negative work-day index: {index}")
        self._extend_to(index)
        return self._index_to_date[index]

    def to_index(self, d: date) -> int:
        """Return the work-day index for a working date.

        For a non-working date, returns the index of the *next* working day.
        """
        d = self._snap_to_working_day(d)
        if d in self._date_to_index:
            return self._date_to_index[d]
        # Extend until we hit it.
        while self._index_to_date[-1] < d:
            self._extend_to(len(self._index_to_date))
        return self._date_to_index[d]

    def add_days(self, base_index: int, n: int) -> int:
        """Add `n` working days (may be negative) to a work-day index."""
        return base_index + n

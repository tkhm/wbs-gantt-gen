from datetime import date

import pytest

from wbsgen.bizcal import WorkdayCalendar
from wbsgen.model import (
    Activity,
    CalendarConfig,
    Constraint,
    Dependency,
    Project,
    ProjectMeta,
    Work,
)
from wbsgen.scheduler import ScheduleError, critical_path, schedule


def _proj(activities, works=None):
    return Project(meta=ProjectMeta(), works=works or [], activities=activities)


def test_fs_basic():
    a = Activity(id="A", name="a", work_id="w", duration=5)
    b = Activity(id="B", name="b", work_id="w", duration=3, depends_on=[Dependency("A")])
    p = _proj([a, b])
    schedule(p)
    assert (a.es, a.ef) == (0, 5)
    assert (b.es, b.ef) == (5, 8)
    assert p.project_duration == 8


def test_fs_with_positive_lag():
    a = Activity(id="A", name="a", work_id="w", duration=5)
    b = Activity(id="B", name="b", work_id="w", duration=3, depends_on=[Dependency("A", "FS", 2)])
    schedule(_proj([a, b]))
    assert (b.es, b.ef) == (7, 10)


def test_fs_negative_lag_overlap():
    a = Activity(id="A", name="a", work_id="w", duration=5)
    b = Activity(id="B", name="b", work_id="w", duration=3, depends_on=[Dependency("A", "FS", -2)])
    schedule(_proj([a, b]))
    assert (b.es, b.ef) == (3, 6)


def test_ss_basic():
    a = Activity(id="A", name="a", work_id="w", duration=5)
    b = Activity(id="B", name="b", work_id="w", duration=3, depends_on=[Dependency("A", "SS", 1)])
    schedule(_proj([a, b]))
    assert (b.es, b.ef) == (1, 4)


def test_ff_basic():
    a = Activity(id="A", name="a", work_id="w", duration=5)
    b = Activity(id="B", name="b", work_id="w", duration=3, depends_on=[Dependency("A", "FF", 0)])
    schedule(_proj([a, b]))
    assert (b.es, b.ef) == (2, 5)


def test_sf_basic():
    a = Activity(id="A", name="a", work_id="w", duration=5)
    b = Activity(id="B", name="b", work_id="w", duration=3, depends_on=[Dependency("A", "SF", 4)])
    schedule(_proj([a, b]))
    assert (b.es, b.ef) == (1, 4)


def test_critical_path_chain():
    a = Activity(id="A", name="a", work_id="w", duration=2)
    b = Activity(id="B", name="b", work_id="w", duration=3, depends_on=[Dependency("A")])
    c = Activity(id="C", name="c", work_id="w", duration=2, depends_on=[Dependency("B")])
    p = _proj([a, b, c])
    schedule(p)
    assert a.critical and b.critical and c.critical
    assert critical_path(p) == ["A", "B", "C"]


def test_total_float_branches():
    a = Activity(id="A", name="a", work_id="w", duration=1)
    b = Activity(id="B", name="b", work_id="w", duration=5, depends_on=[Dependency("A")])
    c = Activity(id="C", name="c", work_id="w", duration=3, depends_on=[Dependency("A")])
    d = Activity(id="D", name="d", work_id="w", duration=1, depends_on=[Dependency("B"), Dependency("C")])
    schedule(_proj([a, b, c, d]))
    assert b.critical and not c.critical
    assert c.total_float == 2


def test_milestone_zero_duration():
    a = Activity(id="A", name="a", work_id="w", duration=3)
    m = Activity(id="M", name="m", work_id="w", duration=0, depends_on=[Dependency("A")])
    b = Activity(id="B", name="b", work_id="w", duration=2, depends_on=[Dependency("M")])
    schedule(_proj([a, m, b]))
    assert (m.es, m.ef) == (3, 3)
    assert (b.es, b.ef) == (3, 5)


def test_cycle_raises():
    a = Activity(id="A", name="a", work_id="w", duration=1, depends_on=[Dependency("B")])
    b = Activity(id="B", name="b", work_id="w", duration=1, depends_on=[Dependency("A")])
    with pytest.raises(ScheduleError):
        schedule(_proj([a, b]))


def test_snet_constraint_pushes_es():
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig(holidays_preset="none"))
    a = Activity(id="A", name="a", work_id="w", duration=5)
    b = Activity(
        id="B",
        name="b",
        work_id="w",
        duration=3,
        depends_on=[Dependency("A")],
        constraint=Constraint(type="SNET", date=date(2026, 6, 22)),
    )
    p = Project(meta=ProjectMeta(start=date(2026, 6, 1)), activities=[a, b])
    schedule(p, cal)
    snet_idx = cal.to_index(date(2026, 6, 22))
    assert b.es == max(5, snet_idx)

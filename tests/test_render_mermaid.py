from datetime import date

from wbsgen.bizcal import WorkdayCalendar
from wbsgen.model import (
    Activity,
    CalendarConfig,
    Dependency,
    Project,
    ProjectMeta,
    Work,
)
from wbsgen.render.mermaid import render_gantt
from wbsgen.scheduler import schedule


def _simple():
    p = Project(
        meta=ProjectMeta(name="T", start=date(2026, 6, 1)),
        works=[
            Work(id="w-1", name="P1", parent_id=None, order=10),
            Work(id="w-2", name="P2", parent_id=None, order=20),
        ],
        activities=[
            Activity(id="a-a", name="alpha", work_id="w-1", duration=5),
            Activity(id="a-b", name="beta", work_id="w-2", duration=3, depends_on=[Dependency("a-a")]),
            Activity(id="a-m", name="done", work_id="w-2", duration=0, depends_on=[Dependency("a-b")]),
        ],
    )
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig(holidays_preset="none"))
    schedule(p, cal)
    return p, cal


def test_gantt_is_single_block():
    p, cal = _simple()
    out = render_gantt(p, cal)
    # Exactly one mermaid gantt block.
    assert out.count("```mermaid") == 1
    assert out.count("gantt") >= 1


def test_no_after_no_excludes():
    p, cal = _simple()
    out = render_gantt(p, cal)
    assert " after " not in out
    assert "excludes" not in out


def test_explicit_dates_present():
    p, cal = _simple()
    out = render_gantt(p, cal)
    assert "2026-06-01" in out


def test_milestone_tag_present_but_no_critical_colour():
    p, cal = _simple()
    out = render_gantt(p, cal)
    # milestone マークは残す
    assert "milestone" in out
    assert ", 0d" in out
    # クリティカルパスの色分けは廃止
    assert ":crit," not in out
    assert ", crit," not in out
    # doing → active も廃止
    assert ":active," not in out
    assert ", active," not in out


def test_section_per_wp_with_wbs_code():
    """Section ヘッダは WP (リーフ work) 単位、WBS code を含む。"""
    p, cal = _simple()
    out = render_gantt(p, cal)
    # _simple() の P1, P2 はどちらも leaf work (= WP)。
    # WBS code は 1, 2 が振られる。
    assert "section 1 P1" in out
    assert "section 2 P2" in out


def test_status_done_renders_done_tag():
    p = Project(
        meta=ProjectMeta(name="T", start=date(2026, 6, 1)),
        works=[Work(id="w-1", name="P", order=10)],
        activities=[
            Activity(id="a-x", name="x", work_id="w-1", duration=3, status="done"),
        ],
    )
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig(holidays_preset="none"))
    schedule(p, cal)
    out = render_gantt(p, cal)
    assert "done" in out  # tag emitted

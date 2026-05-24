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
from wbsgen.render.pert import render_pert
from wbsgen.render.pyramid import render_wbs_pyramid
from wbsgen.scheduler import schedule
from wbsgen.wbscode import compute_wbs_codes


def _proj():
    p = Project(
        meta=ProjectMeta(name="T", start=date(2026, 6, 1)),
        works=[
            Work(id="w-design", name="設計", order=10),
            Work(id="w-design-sub", name="詳細", parent_id="w-design", order=10),
            Work(id="w-impl", name="実装", order=20),
        ],
        activities=[
            Activity(id="a-spec", name="仕様", work_id="w-design-sub", duration=2),
            Activity(id="a-code", name="コード", work_id="w-impl", duration=5, depends_on=[Dependency("a-spec")]),
            Activity(id="a-rev", name="レビュー", work_id="w-impl", duration=1, depends_on=[Dependency("a-code", "FF", 0)]),
        ],
    )
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig(holidays_preset="none"))
    schedule(p, cal)
    return p, compute_wbs_codes(p), cal


def test_pyramid_draws_works_only():
    p, codes, _ = _proj()
    out = render_wbs_pyramid(p, codes)
    assert "flowchart TB" in out
    assert "'curve': 'stepBefore'" in out
    # Work nodes with WBS codes
    assert ">1</b>" in out
    assert ">1.1</b>" in out
    assert ">2</b>" in out
    # Activities must NOT appear (no boxes, no edges)
    assert "a_spec[" not in out
    assert "a_code[" not in out
    assert "w_design_sub --> a_spec" not in out
    assert "w_impl --> a_code" not in out


def test_pyramid_has_project_root_and_connects_l1():
    p, codes, _ = _proj()
    out = render_wbs_pyramid(p, codes)
    assert "__project_root__" in out or "_project_root" in out
    assert "classDef root" in out
    assert "--> w_design" in out
    assert "--> w_impl" in out


def test_pyramid_marks_leaf_works_as_wp():
    """Leaf works (no children) get class `wp` (= ワークパッケージ)."""
    p, codes, _ = _proj()
    out = render_wbs_pyramid(p, codes)
    assert "classDef wp" in out
    # w-design has a child (w-design-sub), so it's NOT a WP
    # w-design-sub and w-impl are leaves → WPs
    assert "w_design_sub" in out
    assert "w_impl" in out


def test_pyramid_omits_critical_colouring():
    """Pyramid is structural-only — no critical/near-critical classes."""
    p, codes, _ = _proj()
    out = render_wbs_pyramid(p, codes)
    assert "classDef critical" not in out
    assert "classDef near" not in out


def test_pyramid_no_activity_artefacts():
    p, codes, _ = _proj()
    out = render_wbs_pyramid(p, codes)
    assert "<small>" not in out
    assert ">2d<" not in out
    assert "classDef activity" not in out


def test_pert_aoa_structure():
    """AOA: ノード = event、矢印 = activity。subgraph は使わない。"""
    p, codes, _ = _proj()
    out = render_pert(p, codes)
    assert "flowchart LR" in out
    # subgraph は廃止
    assert "subgraph" not in out
    # クリティカル矢印は太線
    assert "==>" in out
    # event ノード (e1, e2, ...)
    assert "e1((" in out
    # Start/Goal の表示
    assert '"①"' in out or "①" in out
    assert '"◎"' in out or "◎" in out


def test_pert_activity_edge_has_wp_code_and_duration():
    """各 activity の矢印ラベルに WP code と duration が含まれる。"""
    p, codes, _ = _proj()
    out = render_pert(p, codes)
    # a-spec は work w-design-sub (= WBS 1.1) 配下、duration=2
    assert "1.1 仕様 (2d)" in out


def test_pert_dummy_edge_for_non_fs_dependency():
    """SS/FF/SF や lag を持つ依存は dummy 矢印 (破線) + ラベルで表現。"""
    p = Project(
        meta=ProjectMeta(start=date(2026, 6, 1)),
        works=[Work(id="w", name="W", order=10)],
        activities=[
            Activity(id="a-1", name="one", work_id="w", duration=3),
            Activity(id="a-2", name="two", work_id="w", duration=2, depends_on=[Dependency("a-1", "SS", 1)]),
        ],
    )
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig(holidays_preset="none"))
    schedule(p, cal)
    out = render_pert(p, compute_wbs_codes(p))
    # SS+1d ラベルが dummy 矢印に乗る
    assert "SS+1d" in out
    # 破線矢印 (-.->) で表現
    assert "-.->" in out


def test_pert_critical_path_uses_thick_arrows():
    p, codes, _ = _proj()
    out = render_pert(p, codes)
    # クリティカルパスは ==>、非クリティカルは -->
    assert "==>" in out

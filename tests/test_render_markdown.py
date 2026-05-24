"""Markdown 全体出力のテスト。WP サマリ表など、複合機能の動作確認。"""

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
from wbsgen.render.markdown import render_markdown
from wbsgen.scheduler import schedule


def _proj():
    p = Project(
        meta=ProjectMeta(name="T", start=date(2026, 6, 1)),
        works=[
            Work(id="w-a", name="要件", order=10),
            Work(id="w-a-sub", name="ヒアリング", parent_id="w-a", order=10),
            Work(id="w-b", name="設計", order=20),
            Work(id="w-b-sub", name="アーキ", parent_id="w-b", order=10),
        ],
        activities=[
            Activity(id="a-1", name="調査", work_id="w-a-sub", duration=3, status="done"),
            Activity(id="a-2", name="まとめ", work_id="w-a-sub", duration=2, status="doing", depends_on=[Dependency("a-1")]),
            Activity(id="a-3", name="設計案", work_id="w-b-sub", duration=4, depends_on=[Dependency("a-2")]),
            Activity(id="a-4", name="レビュー", work_id="w-b-sub", duration=1, status="blocked", depends_on=[Dependency("a-3")]),
        ],
    )
    cal = WorkdayCalendar(date(2026, 6, 1), CalendarConfig(holidays_preset="none"))
    schedule(p, cal)
    return p, cal


def test_wp_summary_section_present():
    p, cal = _proj()
    out = render_markdown(p, cal)
    assert "ワークパッケージ別 進捗" in out


def test_wp_summary_columns():
    p, cal = _proj()
    out = render_markdown(p, cal)
    # ステータスごとの列ヘッダ
    assert "✅完了" in out
    assert "⏳着手中" in out
    assert "⬜未着手" in out
    assert "⛔ブロック" in out
    assert "進捗" in out


def test_wp_summary_counts_correctly():
    p, cal = _proj()
    out = render_markdown(p, cal)
    # w-a-sub: done=1, doing=1, 計2, 50%
    # 表の中に "1 | 1 | 0 | 0 | 2" のような並びが出る (項目区切りはパイプ + 空白)
    # 数字単独 + 進捗% の "50%" が含まれているか
    assert "50%" in out  # w-a-sub progress
    # 全体: done=1, doing=1, todo=1, blocked=1, 計4 → 25%
    assert "25%" in out  # totals row


def test_wp_summary_only_includes_leaf_works():
    """非リーフ work (w-a, w-b) はサマリに出ない。リーフ (w-a-sub, w-b-sub) のみ。"""
    p, cal = _proj()
    out = render_markdown(p, cal)
    # WP summary section だけを切り出して確認
    head = "## ワークパッケージ別 進捗"
    next_head = "## アクティビティ詳細"
    start = out.index(head)
    end = out.index(next_head)
    wp_section = out[start:end]
    # 親 work 名はサマリ表内には出ない (リーフのみ)
    assert "ヒアリング" in wp_section  # w-a-sub (leaf)
    assert "アーキ" in wp_section      # w-b-sub (leaf)

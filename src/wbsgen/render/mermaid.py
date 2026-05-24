"""Single-block Mermaid gantt renderer.

Layout (per ユーザー指示):
- Section は **ワークパッケージ (WP = リーフ work) 単位** で区切る
- Section ヘッダに WBS code を付与 (例: `1.1.1 ヒアリング報告`)
- Activity の色は **done のみ** グレー化。critical / doing / blocked の
  色分けはしない (情報過多を避ける)
- Milestone は `milestone` タグで菱形表示

Per plan.md 5.2:
- One gantt block (do not split per WBS package; 視覚的には WP ごとに
  section が分かれるが、Mermaid ブロック自体は 1 つ)
- 明示的な YYYY-MM-DD 日付 (`after` 構文と `excludes weekends` は使わない)

依存関係の矢印は描かない (Mermaid gantt の制約)。PERT 図で補完する。
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from wbsgen.bizcal import WorkdayCalendar
from wbsgen.model import Activity, Project
from wbsgen.render._util import safe_mermaid_id
from wbsgen.wbscode import compute_wbs_codes


def _is_leaf_work(work_id: str, project: Project) -> bool:
    return not any(w.parent_id == work_id for w in project.works)


def _wbs_code_sort_key(code: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in code.split("."))
    except ValueError:
        return (10**9,)


def _activity_calendar_span(
    a: Activity, calendar: WorkdayCalendar
) -> tuple[date, int]:
    """(start_date, calendar_day_span). Milestones return span=0
    with start = prior workday (MSP convention)."""
    if a.duration == 0:
        return calendar.to_date(max(0, a.es - 1)), 0
    start = calendar.to_date(a.es)
    last_workday = calendar.to_date(a.ef - 1)
    span = (last_workday - start).days + 1
    return start, span


_BAD_LABEL = re.compile(r"[:#]")


def _label(name: str) -> str:
    # `:` is the field separator in gantt rows; `#` starts a comment.
    return _BAD_LABEL.sub("：", name)


def render_gantt(project: Project, calendar: WorkdayCalendar) -> str:
    lines: list[str] = ["```mermaid", "gantt"]
    lines.append("    dateFormat YYYY-MM-DD")
    lines.append("    axisFormat %m/%d")
    lines.append(f"    title {_label(project.meta.name)}")
    lines.append("")

    wbs_codes = compute_wbs_codes(project)

    # --- Group activities by WP (leaf work) ---
    by_wp: dict[str, list[Activity]] = defaultdict(list)
    for a in project.activities:
        by_wp[a.work_id].append(a)

    # WP order = WBS code ascending
    wp_works = [w for w in project.works if _is_leaf_work(w.id, project)]
    wp_works.sort(key=lambda w: _wbs_code_sort_key(wbs_codes.get(w.id, "")))

    for wp in wp_works:
        members = by_wp.get(wp.id, [])
        if not members:
            continue
        members_sorted = sorted(members, key=lambda x: (x.es, x.order, x.id))
        code = wbs_codes.get(wp.id, "?")
        lines.append(f"    section {_label(code)} {_label(wp.name)}")
        for a in members_sorted:
            tag = safe_mermaid_id(a.id)
            tags: list[str] = []
            if a.duration == 0:
                tags.append("milestone")
            if a.status == "done":
                tags.append("done")
            tag_prefix = (", ".join(tags) + ", ") if tags else ""
            start_date, span = _activity_calendar_span(a, calendar)
            if a.duration == 0:
                lines.append(
                    f"    {_label(a.name)} :{tag_prefix}{tag}, {start_date.isoformat()}, 0d"
                )
            else:
                lines.append(
                    f"    {_label(a.name)} :{tag_prefix}{tag}, {start_date.isoformat()}, {span}d"
                )
        lines.append("")

    # --- Orphan activities (no resolved WP) ---
    orphan_acts = [
        a for a in project.activities if a.work_id not in {w.id for w in wp_works}
    ]
    if orphan_acts:
        lines.append("    section (未分類)")
        for a in sorted(orphan_acts, key=lambda x: (x.es, x.order, x.id)):
            tag = safe_mermaid_id(a.id)
            tags = []
            if a.duration == 0:
                tags.append("milestone")
            if a.status == "done":
                tags.append("done")
            tag_prefix = (", ".join(tags) + ", ") if tags else ""
            start_date, span = _activity_calendar_span(a, calendar)
            if a.duration == 0:
                lines.append(
                    f"    {_label(a.name)} :{tag_prefix}{tag}, {start_date.isoformat()}, 0d"
                )
            else:
                lines.append(
                    f"    {_label(a.name)} :{tag_prefix}{tag}, {start_date.isoformat()}, {span}d"
                )
        lines.append("")

    lines.append("```")
    return "\n".join(lines)

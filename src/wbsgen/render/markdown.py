"""Markdown renderer (v2).

Layout (per plan.md 5):
1. プロジェクト概要
2. WBS ピラミッド図 (Mermaid flowchart LR)
3. ガント (Mermaid gantt, 単一ブロック)
4. PERT 図 (Mermaid flowchart, 依存ネットワーク)
5. 詳細表 (Markdown)
6. クリティカルパス要約
7. ニア・クリティカル
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from wbsgen.bizcal import WorkdayCalendar
from wbsgen.deps_dsl import format_predecessors
from wbsgen.model import Activity, Project
from wbsgen.render.mermaid import render_gantt
from wbsgen.render.pert import render_pert
from wbsgen.render.pyramid import render_wbs_pyramid
from wbsgen.scheduler import critical_path
from wbsgen.wbscode import compute_wbs_codes


_STATUS_BADGE = {
    "todo": "",
    "doing": "🟢",
    "done": "✅",
    "blocked": "⛔",
}


def _is_leaf_work(work_id: str, project: Project) -> bool:
    return not any(w.parent_id == work_id for w in project.works)


def _strip_leading_h1(md: str) -> str:
    """ファイル冒頭の H1 (タイトル相当) を1行だけ除去する。
    その下の空行・前書き段落は残し、後続の H2 以降に自然に繋ぐ。
    """
    lines = md.split("\n")
    i = 0
    if i < len(lines) and lines[i].lstrip().startswith("# "):
        i = 1
        # 直後の空行も飛ばす
        while i < len(lines) and not lines[i].strip():
            i += 1
    return "\n".join(lines[i:])


def _progress_bar(pct: int, width: int = 10) -> str:
    pct = max(0, min(100, pct))
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _wp_summary_table(project: Project, codes: dict[str, str]) -> str:
    """WP (= leaf work) ごとのステータス集計表を返す。"""
    leaf_ids = {w.id for w in project.works if _is_leaf_work(w.id, project)}

    rows: list[dict] = []
    for w in project.works:
        if w.id not in leaf_ids:
            continue
        acts = [a for a in project.activities if a.work_id == w.id]
        if not acts:
            continue
        counts = {"done": 0, "doing": 0, "todo": 0, "blocked": 0}
        for a in acts:
            counts[a.status] = counts.get(a.status, 0) + 1
        total = len(acts)
        progress = counts["done"] * 100 // total if total > 0 else 0
        rows.append(
            {
                "code": codes.get(w.id, "?"),
                "name": w.name,
                "done": counts["done"],
                "doing": counts["doing"],
                "todo": counts["todo"],
                "blocked": counts["blocked"],
                "total": total,
                "progress": progress,
            }
        )

    def _code_key(c: str) -> tuple[int, ...]:
        try:
            return tuple(int(x) for x in c.split("."))
        except ValueError:
            return (10**9,)

    rows.sort(key=lambda r: _code_key(r["code"]))

    headers = ["WBS", "ワークパッケージ", "✅完了", "⏳着手中", "⬜未着手", "⛔ブロック", "計", "進捗"]
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        bar = _progress_bar(r["progress"])
        out.append(
            f"| {r['code']} | {r['name']} | {r['done']} | {r['doing']} | "
            f"{r['todo']} | {r['blocked']} | {r['total']} | `{bar}` {r['progress']}% |"
        )

    # Totals row
    if rows:
        tot_done = sum(r["done"] for r in rows)
        tot_doing = sum(r["doing"] for r in rows)
        tot_todo = sum(r["todo"] for r in rows)
        tot_blocked = sum(r["blocked"] for r in rows)
        tot_total = sum(r["total"] for r in rows)
        tot_progress = tot_done * 100 // tot_total if tot_total > 0 else 0
        bar = _progress_bar(tot_progress)
        out.append(
            f"| **計** | **全 WP** | **{tot_done}** | **{tot_doing}** | "
            f"**{tot_todo}** | **{tot_blocked}** | **{tot_total}** | `{bar}` **{tot_progress}%** |"
        )

    return "\n".join(out)


def _start_finish(a: Activity, cal: Optional[WorkdayCalendar]) -> tuple[str, str]:
    # Milestone displays on prior workday (MSP convention).
    if cal is None:
        if a.duration == 0:
            d = f"D{max(0, a.es - 1)}"
            return d, d
        return f"D{a.es}", f"D{max(a.es, a.ef - 1)}"
    if a.duration == 0:
        d = cal.to_date(max(0, a.es - 1)).isoformat()
        return d, d
    return cal.to_date(a.es).isoformat(), cal.to_date(max(a.es, a.ef - 1)).isoformat()


def _activity_table(
    project: Project,
    cal: Optional[WorkdayCalendar],
    work_codes: dict[str, str],
) -> str:
    """所属 WP の WBS code を列頭に置く。activity 自身は WBS 番号を持たない。"""
    headers = [
        "WP",
        "ID",
        "名称",
        "状態",
        "所要",
        "先行",
        "ES",
        "EF",
        "TF",
        "FF",
        "開始",
        "終了",
        "CP",
    ]
    rows: list[list[str]] = []
    for a in sorted(project.activities, key=lambda x: (x.es, x.order, x.id)):
        start, finish = _start_finish(a, cal)
        cp = "★" if a.critical else ("✦" if a.near_critical else "")
        wp_code = work_codes.get(a.work_id, "?")
        ms = " ◆" if a.duration == 0 else ""
        status_badge = _STATUS_BADGE.get(a.status, "")
        preds = format_predecessors(a.depends_on) or "—"
        rows.append([
            wp_code,
            f"`{a.id}`",
            a.name + ms,
            f"{status_badge} {a.status}".strip(),
            "0" if a.duration == 0 else str(a.duration),
            preds,
            str(a.es),
            str(a.ef),
            str(a.total_float),
            str(a.free_float),
            start,
            finish,
            cp,
        ])
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def render_markdown(project: Project, calendar: Optional[WorkdayCalendar]) -> str:
    codes = compute_wbs_codes(project)
    project.wbs_codes = codes
    cp = critical_path(project)
    out: list[str] = []

    out.append(f"# {project.meta.name} — WBS / スケジュール")
    out.append("")
    if project.meta.description:
        out.append(project.meta.description)
        out.append("")

    # --- 概要 ---
    unit_label = "営業日" if project.meta.units == "business_days" else "暦日"
    if project.meta.start is not None and calendar is not None:
        start_date = calendar.to_date(0)
        end_date = (
            calendar.to_date(max(0, project.project_duration - 1))
            if project.project_duration > 0
            else start_date
        )
        period_str = f"{start_date.isoformat()} 〜 {end_date.isoformat()}"
    else:
        period_str = f"D0 〜 D{max(0, project.project_duration - 1)}"

    done_count = sum(1 for a in project.activities if a.status == "done")
    doing_count = sum(1 for a in project.activities if a.status == "doing")
    blocked_count = sum(1 for a in project.activities if a.status == "blocked")

    out.append("## 概要")
    out.append("")
    out.append(f"- 期間: {period_str}（{project.project_duration} {unit_label}）")
    out.append(f"- Work: {len(project.works)} / Activity: {len(project.activities)}")
    out.append(f"- クリティカルパス: {len(cp)} 活動 / {project.project_duration} {unit_label}")
    out.append(
        f"- 進捗: ✅ {done_count} 完了 / 🟢 {doing_count} 着手中 / ⛔ {blocked_count} ブロック"
    )
    out.append("")

    # --- WBS ピラミッド ---
    out.append("## WBS（構造の俯瞰）")
    out.append("")
    out.append(render_wbs_pyramid(project, codes))
    out.append("")

    # --- WBS 辞書 (任意) ---
    if project.dictionary_md and project.dictionary_md.strip():
        out.append("## WBS 辞書")
        out.append("")
        out.append(_strip_leading_h1(project.dictionary_md.strip()))
        out.append("")

    # --- ガント ---
    out.append("## ガントチャート（時系列）")
    out.append("")
    if project.meta.start is None or calendar is None:
        out.append(
            "_注: `project.start` が未指定。実日付ガントを出すには project.toml に `start` を設定する。_"
        )
    else:
        out.append(render_gantt(project, calendar))
    out.append("")

    # --- PERT ---
    out.append("## PERT 図（依存ネットワーク）")
    out.append("")
    out.append("_クリティカルパスは太線で表示。`==>` がクリティカル、`-->` が通常。_")
    out.append("")
    out.append(render_pert(project, codes))
    out.append("")

    # --- WP サマリ ---
    out.append("## ワークパッケージ別 進捗")
    out.append("")
    out.append(
        "_WP = WBS の最下層（リーフ work）。アクティビティのステータス集計と進捗を WP 単位で表示。_"
    )
    out.append("")
    out.append(_wp_summary_table(project, codes))
    out.append("")

    # --- 詳細表 ---
    out.append("## アクティビティ詳細")
    out.append("")
    out.append(_activity_table(project, calendar, codes))
    out.append("")
    out.append(
        "凡例: **CP** ★=クリティカル ✦=ニア・クリティカル / "
        "**TF**=トータルフロート **FF**=フリーフロート / "
        "**先行** 例: `a-foo+2` = FS ラグ+2 / `a-bar/SS` = SS / `a-baz/FF-1` = FF ラグ-1"
    )
    out.append("")

    # --- クリティカルパス ---
    out.append("## クリティカルパス")
    out.append("")
    if cp:
        by_id = {a.id: a for a in project.activities}
        cp_names = [f"`{aid}` {by_id[aid].name}" for aid in cp]
        out.append(" → ".join(cp_names))
        out.append("")
        out.append(f"_合計: {project.project_duration} {unit_label}_")
    else:
        out.append("_クリティカルパスを特定できなかった_")
    out.append("")

    # --- ニア・クリティカル ---
    near = [a for a in project.activities if a.near_critical]
    if near:
        out.append("## ニア・クリティカル")
        out.append("")
        for a in sorted(near, key=lambda x: x.total_float):
            out.append(f"- `{a.id}` {a.name} (TF={a.total_float})")
        out.append("")

    return "\n".join(out)

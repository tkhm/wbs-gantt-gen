"""PERT chart in AOA (Arrow Diagramming Method) form.

PMBOK 7 では AON (PDM) が主流だが、古典的 PERT の表記である AOA を
こちらの図では採用する。

  ┌────┐  activity name  ┌────┐
  │ 1  │ ───────────────▶│ 2  │
  └────┘                 └────┘

- ノード = イベント (時点)
- 実線矢印 = activity。ラベルに WP code + 名前 + duration
- 破線矢印 = dummy (依存関係の表現のみ。0 duration)
- 太い矢印 (==>) = クリティカルパス上の activity

実装ノート
----------
AOA は本来 FS (= 終了→開始, lag=0) のみネイティブ表現可能。SS/FF/SF や
lag は AOA の標準記法に存在しない。本実装ではそれらを次のように近似:
- 依存タイプ・lag は dummy 矢印のラベルに `SS+2` などと書く
- 配置上は predecessor.end_event → successor.start_event の dummy として描く
  (= 実際の制約関係とはずれがあるが、依存の存在は読み取れる)

正確な依存タイプとフロート値は詳細表とガントで確認すること。
"""

from __future__ import annotations

from collections import defaultdict

from wbsgen.model import Activity, Dependency, Project
from wbsgen.render._util import mermaid_escape_label
from wbsgen.scheduler import _topological_sort


def _dep_label(d: Dependency) -> str:
    if d.type == "FS" and d.lag == 0:
        return "dummy"
    s = d.type
    if d.lag != 0:
        s += f"{d.lag:+d}d"
    return s


def render_pert(project: Project, wbs_codes: dict[str, str]) -> str:
    activity_ids = {a.id for a in project.activities}
    by_id = {a.id: a for a in project.activities}

    successors_of: dict[str, list[tuple[str, Dependency]]] = defaultdict(list)
    for a in project.activities:
        for dep in a.depends_on:
            if dep.predecessor_id in activity_ids:
                successors_of[dep.predecessor_id].append((a.id, dep))

    sorted_ids = _topological_sort(project)

    PROJECT_START_EVT = 1
    start_event: dict[str, int] = {}
    end_event: dict[str, int] = {}
    counter = [2]

    def new_evt() -> int:
        e = counter[0]
        counter[0] += 1
        return e

    # 各 activity の start_event / end_event を割り当てる
    for aid in sorted_ids:
        a = by_id[aid]
        pred_end_evts: set[int] = set()
        for dep in a.depends_on:
            if dep.predecessor_id in end_event:
                pred_end_evts.add(end_event[dep.predecessor_id])

        # predecessor が無い → プロジェクト開始イベントを共有
        if not pred_end_evts:
            start_event[aid] = PROJECT_START_EVT
        elif (
            len(pred_end_evts) == 1
            and all(d.type == "FS" and d.lag == 0 for d in a.depends_on)
        ):
            # 単一 predecessor + 全部 FS lag=0 → predecessor の end と event を共有
            start_event[aid] = next(iter(pred_end_evts))
        else:
            # 複数 predecessor or 非 FS / lag あり → 新規 event + dummy で接続
            start_event[aid] = new_evt()
        end_event[aid] = new_evt()

    # プロジェクト終端 event を統合
    terminal_aids = [aid for aid in activity_ids if not successors_of[aid]]
    project_end_evt: int | None = None
    if len(terminal_aids) == 1:
        project_end_evt = end_event[terminal_aids[0]]
    elif terminal_aids:
        project_end_evt = new_evt()

    # --- 描画 ---
    lines: list[str] = ["```mermaid", "flowchart LR"]

    all_events = (
        {PROJECT_START_EVT} | set(start_event.values()) | set(end_event.values())
    )
    if project_end_evt is not None:
        all_events.add(project_end_evt)
    for e in sorted(all_events):
        if e == PROJECT_START_EVT:
            lines.append(f'    e{e}(("①"))')
        elif e == project_end_evt:
            lines.append(f'    e{e}(("◎"))')
        else:
            lines.append(f"    e{e}(({e}))")

    # Activity edges (実線)
    for aid in sorted_ids:
        a = by_id[aid]
        se = start_event[aid]
        ee = end_event[aid]
        wp_code = wbs_codes.get(a.work_id, "?")
        if a.duration == 0:
            label = f"{wp_code} {mermaid_escape_label(a.name)} ◆"
        else:
            label = f"{wp_code} {mermaid_escape_label(a.name)} ({a.duration}d)"
        arrow = "==>" if a.critical else "-->"
        lines.append(f'    e{se} {arrow}|"{label}"| e{ee}')

    # Dummy edges (破線) — predecessor の end_event から successor の start_event
    for aid in sorted_ids:
        a = by_id[aid]
        se = start_event[aid]
        for dep in a.depends_on:
            if dep.predecessor_id not in end_event:
                continue
            pe = end_event[dep.predecessor_id]
            if pe == se:
                # event を共有している (主 edge で接続済み)
                continue
            label = _dep_label(dep)
            lines.append(f'    e{pe} -.->|{label}| e{se}')

    # 複数終端の統合 dummy
    if project_end_evt is not None and len(terminal_aids) > 1:
        for taid in terminal_aids:
            te = end_event[taid]
            if te != project_end_evt:
                lines.append(f'    e{te} -.->|dummy| e{project_end_evt}')

    # --- styling ---
    lines.append("")
    lines.append("    classDef evt fill:#f8fafc,stroke:#1e293b,color:#0f172a")
    lines.append("    classDef startend fill:#1e3a8a,stroke:#0b1a3d,color:#ffffff,stroke-width:2px")
    evt_ids = [f"e{e}" for e in sorted(all_events)]
    if evt_ids:
        lines.append(f"    class {','.join(evt_ids)} evt")
    boundary_ids = [f"e{PROJECT_START_EVT}"]
    if project_end_evt is not None and project_end_evt != PROJECT_START_EVT:
        boundary_ids.append(f"e{project_end_evt}")
    lines.append(f"    class {','.join(boundary_ids)} startend")

    lines.append("```")
    return "\n".join(lines)

"""WBS pyramid (Mermaid flowchart TB, top→down).

ミロセビッチ式の表現:
- L1, L2 は独立 box (org-chart 風)
- L3 以下は L2 box の直下に置く「透明な箱」1 つにまとめ、WBS 番号付き
  箇条書きで表示する

         [Project (L0)]
         /     |     \\
      [L1]   [L1]   [L1]
      / \\           |
   [L2]  [L2]      [L2]      ← 子孫を持たない L2 = WP
    │
   ┌┄┄┄┄┄┄┄┄┄┐
   ┆ 1.1.1 …  ┆               ← 透明 box (点線枠)。中身は L3+ (WP) を箇条書き
   ┆ 1.1.2 …  ┆
   └┄┄┄┄┄┄┄┄┄┘

PMBOK 上:
- リーフ work = ワークパッケージ (WP)
- 小規模案件は L2 = WP のままで OK (透明 box は出ない)
- 中〜大規模案件で L3+ がある場合のみ透明 box が出現する

依存・順序・日程は WBS には載せない (ガント・PERT 側)。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from wbsgen.model import Project, Work
from wbsgen.render._util import mermaid_escape_label, safe_mermaid_id


_ROOT_ID = "__project_root__"


def _depths(project: Project) -> dict[str, int]:
    by_id = {w.id: w for w in project.works}
    depth: dict[str, int] = {}

    def calc(wid: str) -> int:
        if wid in depth:
            return depth[wid]
        w = by_id.get(wid)
        if w is None or w.parent_id is None:
            depth[wid] = 1
        else:
            depth[wid] = calc(w.parent_id) + 1
        return depth[wid]

    for w in project.works:
        calc(w.id)
    return depth


def _descendants(project: Project, root_id: str) -> list[Work]:
    """Return all works whose parent chain reaches root_id (excluding root)."""
    by_id = {w.id: w for w in project.works}
    result: list[Work] = []

    def collect(parent_id: str) -> None:
        for w in project.works:
            if w.parent_id == parent_id:
                result.append(w)
                collect(w.id)

    collect(root_id)
    return result


def render_wbs_pyramid(project: Project, wbs_codes: dict[str, str]) -> str:
    lines: list[str] = [
        "```mermaid",
        "%%{init: {'flowchart': {'curve': 'stepBefore'}}}%%",
        "flowchart TB",
    ]

    depth = _depths(project)

    # --- Project root (L0) ---
    root_nid = safe_mermaid_id(_ROOT_ID)
    root_label = mermaid_escape_label(project.meta.name)
    lines.append(f'    {root_nid}["{root_label}"]')

    # --- L1 & L2 work nodes (independent boxes) ---
    upper_ids: set[str] = set()
    wp_ids: set[str] = set()  # leaf works at depth ≤ 2 only (L3+ live inside group)
    for w in project.works:
        if depth[w.id] > 2:
            continue
        upper_ids.add(w.id)
        nid = safe_mermaid_id(w.id)
        code = wbs_codes.get(w.id, "?")
        label = f"<b>{code}</b> {mermaid_escape_label(w.name)}"
        lines.append(f'    {nid}["{label}"]')
        # Mark as WP if it has no children at all (no further work descendants).
        has_children = any(other.parent_id == w.id for other in project.works)
        if not has_children:
            wp_ids.add(w.id)

    # --- L3+ group boxes (one per L2 that has descendants) ---
    group_ids: list[str] = []
    l2_with_descendants: list[Work] = []
    for w in project.works:
        if depth[w.id] != 2:
            continue
        descs = _descendants(project, w.id)
        if not descs:
            continue
        l2_with_descendants.append(w)
        # Sort by WBS code so the listing is stable & numbered ascending.
        descs.sort(key=lambda d: [int(x) for x in wbs_codes.get(d.id, "0").split(".")])
        items = [
            f"<b>{wbs_codes.get(d.id, '?')}</b> {mermaid_escape_label(d.name)}"
            for d in descs
        ]
        label = "<br/>".join(items)
        group_nid = safe_mermaid_id(w.id + "__l3group")
        group_ids.append(group_nid)
        lines.append(f'    {group_nid}["{label}"]')

    # --- Edges: root → L1 ---
    for w in project.works:
        if w.parent_id is None and depth[w.id] == 1:
            lines.append(f"    {root_nid} --> {safe_mermaid_id(w.id)}")

    # --- Edges: L1 → L2 ---
    for w in project.works:
        if w.parent_id and depth[w.id] == 2:
            lines.append(
                f"    {safe_mermaid_id(w.parent_id)} --> {safe_mermaid_id(w.id)}"
            )

    # --- Edges: L2 → its L3 group ---
    for w in l2_with_descendants:
        group_nid = safe_mermaid_id(w.id + "__l3group")
        lines.append(f"    {safe_mermaid_id(w.id)} --> {group_nid}")

    # --- classDef ---
    lines.append("")
    lines.append("    classDef root fill:#1e3a8a,stroke:#0b1a3d,color:#ffffff,stroke-width:2px")
    lines.append("    classDef work fill:#dbeafe,stroke:#1e3a8a,color:#0b1a3d")
    lines.append("    classDef wp fill:#93c5fd,stroke:#1e3a8a,color:#0b1a3d,stroke-width:2px")
    lines.append(
        "    classDef l3group fill:none,stroke:#9ca3af,stroke-dasharray:3 3,color:#1f2937,text-align:left"
    )

    lines.append(f"    class {root_nid} root")

    work_non_wp = [safe_mermaid_id(wid) for wid in upper_ids if wid not in wp_ids]
    if work_non_wp:
        lines.append(f"    class {','.join(work_non_wp)} work")
    wp_safe = [safe_mermaid_id(wid) for wid in wp_ids]
    if wp_safe:
        lines.append(f"    class {','.join(wp_safe)} wp")
    if group_ids:
        lines.append(f"    class {','.join(group_ids)} l3group")

    lines.append("```")
    return "\n".join(lines)

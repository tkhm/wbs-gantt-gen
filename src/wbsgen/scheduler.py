"""Critical Path Method (CPM) scheduler.

Pure integer work-day arithmetic. Calendar projection happens at the
render layer.

PMBOK terms / formulas
----------------------
For an activity A with duration d, and a predecessor P with dependency
type t and lag L:

- FS (Finish-to-Start):   A.ES >= P.EF + L
- SS (Start-to-Start):    A.ES >= P.ES + L
- FF (Finish-to-Finish):  A.EF >= P.EF + L   (→ A.ES >= P.EF + L − d)
- SF (Start-to-Finish):   A.EF >= P.ES + L   (→ A.ES >= P.ES + L − d)

A.EF = A.ES + d (half-open interval; for milestones d=0 so EF=ES).

Total Float:  TF = LS − ES = LF − EF.
Free Float:   FF = max Δ such that delaying A by Δ doesn't push any
              successor's ES. Per successor s with dep type t and lag L:
  FS: Δ <= s.ES − A.EF − L
  SS: Δ <= s.ES − A.ES − L
  FF: Δ <= s.EF − A.EF − L
  SF: Δ <= s.EF − A.ES − L
"""

from __future__ import annotations

from typing import Optional

from wbsgen.bizcal import WorkdayCalendar
from wbsgen.model import Activity, Project


class ScheduleError(Exception):
    pass


def schedule(project: Project, calendar: Optional[WorkdayCalendar] = None) -> None:
    """Compute ES/EF/LS/LF/TF/FF and critical flags in place.

    `calendar` is required to honour date-based SNET/SNLT/FNET/FNLT
    constraints. When omitted, such constraints are silently skipped
    (relative-day mode).
    """
    sorted_ids = _topological_sort(project)
    by_id: dict[str, Activity] = {a.id: a for a in project.activities}

    # --- Forward pass ---
    for aid in sorted_ids:
        a = by_id[aid]
        d = a.effective_duration
        es = 0
        for dep in a.depends_on:
            pred = by_id.get(dep.predecessor_id)
            if pred is None:
                raise ScheduleError(
                    f"activity {aid}: undefined predecessor {dep.predecessor_id}"
                )
            if dep.type == "FS":
                es = max(es, pred.ef + dep.lag)
            elif dep.type == "SS":
                es = max(es, pred.es + dep.lag)
            elif dep.type == "FF":
                es = max(es, pred.ef + dep.lag - d)
            elif dep.type == "SF":
                es = max(es, pred.es + dep.lag - d)
        # Apply constraints (currently SNET / FNET / SNLT / FNLT only nudge ES;
        # SNLT / FNLT are warned but not enforced for late dates in MVP).
        if a.constraint and calendar is not None:
            c_idx = calendar.to_index(a.constraint.date)
            if a.constraint.type == "SNET":
                es = max(es, c_idx)
            elif a.constraint.type == "FNET":
                # EF >= c_idx  →  ES >= c_idx - d
                es = max(es, c_idx - d)
            # SNLT / FNLT are deadline-like; honoured in backward pass logic
            # would lower LF, but to keep MVP focused on critical path we
            # treat them as informational only.
        a.es = es
        a.ef = es + d

    # --- Project duration ---
    project.project_duration = (
        max((a.ef for a in project.activities), default=0)
    )

    # --- Successor map for backward pass ---
    successors: dict[str, list[tuple[Activity, str, int]]] = {
        a.id: [] for a in project.activities
    }
    for a in project.activities:
        for dep in a.depends_on:
            successors[dep.predecessor_id].append((a, dep.type, dep.lag))

    # --- Backward pass ---
    for aid in reversed(sorted_ids):
        a = by_id[aid]
        d = a.effective_duration
        succs = successors[a.id]
        if not succs:
            lf = project.project_duration
        else:
            lf_candidates: list[int] = []
            for s, t, L in succs:
                if t == "FS":
                    # FS: s.ES >= a.EF + L  →  a.EF <= s.LS - L  (LS_s = succ's LS)
                    lf_candidates.append(s.ls - L)
                elif t == "SS":
                    # SS: s.ES >= a.ES + L  →  a.ES <= s.LS - L  →  a.LF <= s.LS - L + d
                    lf_candidates.append((s.ls - L) + d)
                elif t == "FF":
                    # FF: s.EF >= a.EF + L  →  a.EF <= s.LF - L
                    lf_candidates.append(s.lf - L)
                elif t == "SF":
                    # SF: s.EF >= a.ES + L  →  a.ES <= s.LF - L  →  a.LF <= s.LF - L + d
                    lf_candidates.append((s.lf - L) + d)
            lf = min(lf_candidates)
        a.lf = lf
        a.ls = lf - d

    # --- Total / Free Float, Critical, Near-Critical ---
    threshold = project.meta.near_critical_threshold
    for a in project.activities:
        a.total_float = a.ls - a.es
        d = a.effective_duration
        ff_candidates: list[int] = []
        for s, t, L in successors[a.id]:
            if t == "FS":
                ff_candidates.append(s.es - a.ef - L)
            elif t == "SS":
                ff_candidates.append(s.es - a.es - L)
            elif t == "FF":
                ff_candidates.append(s.ef - a.ef - L)
            elif t == "SF":
                ff_candidates.append(s.ef - a.es - L)
        if ff_candidates:
            a.free_float = max(0, min(ff_candidates))
        else:
            # Terminal: free float = total float (PMBOK convention varies; MS Project uses TF)
            a.free_float = a.total_float
        a.critical = a.total_float == 0
        a.near_critical = 0 < a.total_float <= threshold


def _topological_sort(project: Project) -> list[str]:
    """Kahn's algorithm. Raises ScheduleError on cycle."""
    activity_ids = {a.id for a in project.activities}
    indeg: dict[str, int] = {aid: 0 for aid in activity_ids}
    edges: dict[str, list[str]] = {aid: [] for aid in activity_ids}
    for a in project.activities:
        for dep in a.depends_on:
            if dep.predecessor_id not in activity_ids:
                continue
            edges[dep.predecessor_id].append(a.id)
            indeg[a.id] += 1

    queue: list[str] = sorted([aid for aid, d in indeg.items() if d == 0])
    result: list[str] = []
    while queue:
        u = queue.pop(0)
        result.append(u)
        for v in sorted(edges[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    if len(result) != len(activity_ids):
        raise ScheduleError(
            "dependency cycle: cannot topologically sort. Use `wbsgen check` "
            "for a more specific diagnosis."
        )
    return result


def critical_path(project: Project) -> list[str]:
    """Return one critical path as a list of activity IDs in order.

    Picks the longest chain through critical activities.
    """
    critical = {a.id for a in project.activities if a.critical}
    if not critical:
        return []

    by_id = {a.id: a for a in project.activities}
    # Build successor map restricted to critical activities
    succ_map: dict[str, list[str]] = {aid: [] for aid in critical}
    for a in project.activities:
        if a.id not in critical:
            continue
        for dep in a.depends_on:
            if dep.predecessor_id in critical:
                succ_map[dep.predecessor_id].append(a.id)

    # Find roots (critical activities with no critical predecessor)
    has_critical_pred = {aid: False for aid in critical}
    for u, succs in succ_map.items():
        for v in succs:
            has_critical_pred[v] = True
    roots = [aid for aid, has in has_critical_pred.items() if not has]
    if not roots:
        roots = sorted(critical)

    # DFS to find the longest path (by effective duration sum)
    best_path: list[str] = []
    best_len = -1

    def dfs(node: str, path: list[str], length: int) -> None:
        nonlocal best_path, best_len
        succs = succ_map[node]
        if not succs:
            if length > best_len:
                best_len = length
                best_path = list(path)
            return
        for v in succs:
            path.append(v)
            dfs(v, path, length + by_id[v].effective_duration)
            path.pop()

    for r in sorted(roots, key=lambda x: by_id[x].es):
        dfs(r, [r], by_id[r].effective_duration)

    return best_path

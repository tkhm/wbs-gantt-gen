"""Semantic validation (v2: TSV / Work-Activity split).

Checks:
- Duplicate IDs across works/activities (after auto-ID assignment)
- Work parent_id FK resolves, no cycle in parent chain
- Activity.work_id FK resolves
- Activity self-dependency
- Predecessor ID references resolve
- Dependency cycle (returns members in order)
- Negative duration
- Lag sanity (negative lag larger than predecessor duration → warn)
- Milestone (duration=0) with no successor → warn (informational)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from wbsgen.model import Project


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    where: str
    message: str

    def format(self) -> str:
        return f"[{self.severity.upper()}] {self.where}: {self.message}"


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, issue: Issue) -> None:
        if issue.severity == "error":
            self.errors.append(issue)
        else:
            self.warnings.append(issue)

    def format(self) -> str:
        lines: list[str] = []
        for e in self.errors:
            lines.append(e.format())
        for w in self.warnings:
            lines.append(w.format())
        return "\n".join(lines)


def validate(project: Project) -> ValidationResult:
    result = ValidationResult()

    work_ids = {w.id for w in project.works}
    activity_ids = {a.id for a in project.activities}

    # --- Duplicate IDs across works + activities ---
    seen: dict[str, str] = {}
    for w in project.works:
        if w.id in seen:
            result.add(
                Issue("error", f"works[{w.id}]", f"duplicate id (also {seen[w.id]})")
            )
        else:
            seen[w.id] = "works"
    for a in project.activities:
        if a.id in seen:
            result.add(
                Issue("error", f"activities[{a.id}]", f"duplicate id (also {seen[a.id]})")
            )
        else:
            seen[a.id] = "activities"

    # --- Work parent FK + cycle ---
    for w in project.works:
        if w.parent_id is not None and w.parent_id not in work_ids:
            result.add(
                Issue("error", f"works[{w.id}]", f"parent_id '{w.parent_id}' not found")
            )
    for w in project.works:
        chain: list[str] = []
        cur: Optional[str] = w.id
        seen_chain: set[str] = set()
        guard = 0
        while cur is not None:
            if cur in seen_chain:
                result.add(
                    Issue(
                        "error",
                        f"works[{w.id}]",
                        "parent chain cycle: " + " -> ".join(chain + [cur]),
                    )
                )
                break
            seen_chain.add(cur)
            chain.append(cur)
            node = project.work_by_id(cur)
            if node is None:
                break
            cur = node.parent_id
            guard += 1
            if guard > 10_000:
                result.add(Issue("error", f"works[{w.id}]", "parent chain too deep"))
                break

    # --- Activity.work_id FK ---
    for a in project.activities:
        if a.work_id not in work_ids:
            result.add(
                Issue("error", f"activities[{a.id}]", f"work_id '{a.work_id}' not found")
            )

    # --- Dependency FK + self-dep ---
    for a in project.activities:
        for dep in a.depends_on:
            if dep.predecessor_id == a.id:
                result.add(
                    Issue("error", f"activities[{a.id}]", "depends on itself")
                )
            if dep.predecessor_id not in activity_ids:
                result.add(
                    Issue(
                        "error",
                        f"activities[{a.id}]",
                        f"predecessor '{dep.predecessor_id}' not found",
                    )
                )

    # --- Negative duration ---
    for a in project.activities:
        if a.duration < 0:
            result.add(
                Issue("error", f"activities[{a.id}]", f"negative duration {a.duration}")
            )

    # --- Lag sanity ---
    for a in project.activities:
        for dep in a.depends_on:
            pred = project.activity_by_id(dep.predecessor_id)
            if pred is None:
                continue
            if dep.lag < 0 and -dep.lag > pred.duration:
                result.add(
                    Issue(
                        "warning",
                        f"activities[{a.id}]",
                        f"negative lag ({dep.lag}) exceeds predecessor "
                        f"'{pred.id}' duration ({pred.duration})",
                    )
                )

    # --- Dependency cycle (only when refs resolve) ---
    refs_broken = any(
        ("not found" in e.message or "depends on itself" in e.message)
        for e in result.errors
    )
    if not refs_broken:
        cycle = _find_dependency_cycle(project)
        if cycle:
            result.add(
                Issue(
                    "error",
                    "schedule",
                    "dependency cycle: " + " -> ".join(cycle + [cycle[0]]),
                )
            )

    # --- Milestone with no successor (informational) ---
    succ_map: dict[str, list[str]] = {a.id: [] for a in project.activities}
    for a in project.activities:
        for dep in a.depends_on:
            if dep.predecessor_id in succ_map:
                succ_map[dep.predecessor_id].append(a.id)
    for a in project.activities:
        if a.duration == 0 and not succ_map.get(a.id):
            result.add(
                Issue(
                    "warning",
                    f"activities[{a.id}]",
                    "milestone (duration=0) has no successor (informational)",
                )
            )

    return result


def _find_dependency_cycle(project: Project) -> Optional[list[str]]:
    graph: dict[str, list[str]] = {
        a.id: [d.predecessor_id for d in a.depends_on] for a in project.activities
    }
    color: dict[str, int] = {a: 0 for a in graph}
    parent: dict[str, str] = {}

    def dfs(u: str) -> Optional[list[str]]:
        color[u] = 1
        for v in graph.get(u, []):
            if v not in color:
                continue
            if color[v] == 0:
                parent[v] = u
                cyc = dfs(v)
                if cyc is not None:
                    return cyc
            elif color[v] == 1:
                path = [v]
                cur = u
                while cur != v:
                    path.append(cur)
                    cur = parent.get(cur, v)
                path.reverse()
                return path
        color[u] = 2
        return None

    for node in list(graph.keys()):
        if color[node] == 0:
            cyc = dfs(node)
            if cyc is not None:
                return cyc
    return None

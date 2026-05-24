"""WBS code computation (display-only).

`compute_wbs_codes(project)` → {work_id: "X.Y.Z"} —
walks the Work tree (parent_id + order) and assigns codes depth-first.

Activities are not part of the WBS structure (PMBOK separates the WBS
from the Activity List), so this module covers works only. Activities
are referenced by their own ID in the detail table; the WBS column in
that table shows the **parent WP** code, not an activity-specific code.

Codes are NOT persisted to the SSoT; they re-compute whenever the
tree or row order changes.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from wbsgen.model import Project, Work


def compute_wbs_codes(project: Project) -> dict[str, str]:
    """Return {work_id: 'X.Y.Z'}."""
    children: dict[Optional[str], list[Work]] = defaultdict(list)
    for w in project.works:
        children[w.parent_id].append(w)
    for siblings in children.values():
        siblings.sort(key=lambda w: (w.order, w.name))

    codes: dict[str, str] = {}

    def walk(parent: Optional[str], prefix: list[int]) -> None:
        for idx, w in enumerate(children.get(parent, []), start=1):
            code = ".".join(str(n) for n in prefix + [idx])
            codes[w.id] = code
            walk(w.id, prefix + [idx])

    walk(None, [])
    return codes

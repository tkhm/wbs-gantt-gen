"""Domain model (v2: TSV-based).

PMBOK terms:
- Work: WBS要素（成果物の単位、階層構造を持つ）
- Activity: スケジュール・アクティビティ（葉、duration と依存を持つ）
- Dependency: 依存関係（FS/SS/FF/SF + lag）
- Constraint: スケジュール制約（SNET など、現状未使用）

All schedule values (ES/EF/LS/LF/TF/FF) are integer work-day indices.
The Calendar layer (bizcal.py) projects to/from real dates.

IDs are immutable strings, conventionally `w-...` for Work and
`a-...` for Activity. They are populated by the loader when blank.
WBS codes (1.1.1) are NOT stored; they are computed at render time
from the parent_id + order tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

DependencyType = Literal["FS", "SS", "FF", "SF"]
ConstraintType = Literal["SNET", "SNLT", "FNET", "FNLT"]
Status = Literal["todo", "doing", "done", "blocked"]


@dataclass
class Dependency:
    predecessor_id: str
    type: DependencyType = "FS"
    lag: int = 0


@dataclass
class Constraint:
    type: ConstraintType
    date: date


@dataclass
class Work:
    """WBS の中間ノード（成果物単位）。leaf であってもよい。"""
    id: str
    name: str
    parent_id: Optional[str] = None
    order: int = 0


@dataclass
class Activity:
    id: str
    name: str
    work_id: str          # required: which Work this activity belongs to
    order: int = 0
    duration: int = 1     # business days; 0 = milestone
    predecessors_raw: str = ""           # original DSL string for round-trip
    depends_on: list[Dependency] = field(default_factory=list)
    status: Status = "todo"
    constraint: Optional[Constraint] = None

    # Computed by scheduler (work-day indices, 0-based)
    es: int = 0
    ef: int = 0
    ls: int = 0
    lf: int = 0
    total_float: int = 0
    free_float: int = 0
    critical: bool = False
    near_critical: bool = False

    @property
    def milestone(self) -> bool:
        return self.duration == 0

    @property
    def effective_duration(self) -> int:
        return self.duration


@dataclass
class CalendarConfig:
    working_days: list[str] = field(
        default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"]
    )
    holidays_preset: str = "jp"  # "jp" | "none"
    holidays: list[date] = field(default_factory=list)


@dataclass
class ProjectMeta:
    """Project-level settings, read from a small project.toml or
    embedded in CLI args. Kept minimal."""
    name: str = "(untitled project)"
    description: Optional[str] = None
    start: Optional[date] = None
    units: Literal["business_days", "calendar_days"] = "business_days"
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    near_critical_threshold: int = 2


@dataclass
class Project:
    meta: ProjectMeta = field(default_factory=ProjectMeta)
    works: list[Work] = field(default_factory=list)
    activities: list[Activity] = field(default_factory=list)
    dictionary_md: Optional[str] = None  # wbs-dictionary.md の中身 (任意)

    # Computed
    project_duration: int = 0
    wbs_codes: dict[str, str] = field(default_factory=dict)
        # work_id -> "1.2.3" (computed at render time)

    def work_by_id(self, wid: str) -> Optional[Work]:
        for w in self.works:
            if w.id == wid:
                return w
        return None

    def activity_by_id(self, aid: str) -> Optional[Activity]:
        for a in self.activities:
            if a.id == aid:
                return a
        return None

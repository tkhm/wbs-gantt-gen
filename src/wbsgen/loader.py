"""TSV loader: works.tsv + activities.tsv + project.toml → Project.

Project layout
--------------
<project_dir>/
    project.toml      # meta (name, start, calendar)
    works.tsv         # WBS hierarchy (intermediate + leaf works)
    activities.tsv    # schedule activities (with predecessors DSL)

Behavior
--------
- Blank `id` cells are populated by slugifying `name`. Generated IDs
  are guaranteed unique (collision → `-2`, `-3`, ...).
- Blank `order` cells are populated by row order × 10 per sibling group.
- When `rewrite_order=True`, populated `id` / `order` columns are
  written back to disk (atomic replace). Other columns are preserved
  verbatim from the original file.
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

from wbsgen.deps_dsl import DSLError, parse_predecessors
from wbsgen.ids import assign_id
from wbsgen.model import (
    Activity,
    CalendarConfig,
    Project,
    ProjectMeta,
    Status,
    Work,
)


class LoadError(Exception):
    pass


WORKS_COLS = ["id", "parent_id", "order", "name"]
ACTIVITIES_COLS = [
    "work_id",
    "id",
    "order",
    "name",
    "duration",
    "predecessors",
    "status",
]

_VALID_STATUSES: set[str] = {"todo", "doing", "done", "blocked"}


def _read_tsv(path: Path, expected_cols: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        raise LoadError(f"missing file: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames is None:
            raise LoadError(f"{path}: empty file or missing header row")
        # Strip BOM and whitespace from headers
        cleaned_headers = [
            (h or "").lstrip("﻿").strip() for h in reader.fieldnames
        ]
        unknown = [h for h in cleaned_headers if h and h not in expected_cols]
        if unknown:
            raise LoadError(
                f"{path}: unknown columns: {unknown}. expected subset of {expected_cols}"
            )
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {
                (k or "").lstrip("﻿").strip(): (v or "").strip()
                for k, v in raw.items()
            }
            # Skip rows that are entirely blank
            if not any(row.values()):
                continue
            rows.append(row)
        return rows


def _load_meta(path: Path) -> ProjectMeta:
    if not path.exists():
        # meta is optional; fall back to defaults
        return ProjectMeta()
    with path.open("rb") as f:
        data = tomllib.load(f)
    p = data.get("project", {})
    cal_raw = p.get("calendar", {}) or {}

    def _to_date(v: Any) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            return date.fromisoformat(v)
        raise LoadError(f"invalid date value: {v!r}")

    cal = CalendarConfig(
        working_days=list(
            cal_raw.get("working_days", ["mon", "tue", "wed", "thu", "fri"])
        ),
        holidays_preset=cal_raw.get("holidays_preset", "jp"),
        holidays=[_to_date(h) for h in cal_raw.get("holidays", []) if h is not None],  # type: ignore[misc]
    )
    return ProjectMeta(
        name=p.get("name", "(untitled project)"),
        description=p.get("description"),
        start=_to_date(p.get("start")),
        units=p.get("units", "business_days"),
        calendar=cal,
        near_critical_threshold=int(p.get("near_critical_threshold", 2)),
    )


def _build_works(rows: list[dict[str, str]]) -> list[Work]:
    works: list[Work] = []
    for r in rows:
        if not r.get("name"):
            raise LoadError(f"works row missing required 'name': {r}")
        works.append(
            Work(
                id=r.get("id", "") or "",
                name=r["name"],
                parent_id=r.get("parent_id") or None,
                order=int(r["order"]) if r.get("order") else 0,
            )
        )
    return works


def _build_activities(rows: list[dict[str, str]]) -> list[Activity]:
    activities: list[Activity] = []
    for r in rows:
        if not r.get("name"):
            raise LoadError(f"activities row missing required 'name': {r}")
        if not r.get("work_id"):
            raise LoadError(f"activities row missing required 'work_id': {r['name']}")
        dur_raw = r.get("duration", "")
        if not dur_raw:
            raise LoadError(
                f"activities row missing required 'duration': {r['name']}"
            )
        try:
            dur = int(dur_raw)
        except ValueError as e:
            raise LoadError(f"invalid duration for {r['name']}: {dur_raw!r}") from e
        status_raw = (r.get("status") or "todo").strip()
        if status_raw not in _VALID_STATUSES:
            raise LoadError(
                f"invalid status for {r['name']}: {status_raw!r} "
                f"(expected one of {sorted(_VALID_STATUSES)})"
            )
        activities.append(
            Activity(
                id=r.get("id", "") or "",
                name=r["name"],
                work_id=r["work_id"],
                order=int(r["order"]) if r.get("order") else 0,
                duration=dur,
                predecessors_raw=r.get("predecessors", "") or "",
                status=status_raw,  # type: ignore[arg-type]
            )
        )
    return activities


def _assign_missing_ids_works(works: list[Work]) -> None:
    existing = {w.id for w in works if w.id}
    for w in works:
        if not w.id:
            w.id = assign_id(w.name, "w-", existing)
            existing.add(w.id)


def _assign_missing_ids_activities(activities: list[Activity]) -> None:
    existing = {a.id for a in activities if a.id}
    for a in activities:
        if not a.id:
            a.id = assign_id(a.name, "a-", existing)
            existing.add(a.id)


def _renumber_order_works(works: list[Work]) -> None:
    """Case 1: row order is authoritative; renumber order to 10-step."""
    groups: dict[Optional[str], list[Work]] = defaultdict(list)
    for w in works:
        groups[w.parent_id].append(w)
    for siblings in groups.values():
        for i, w in enumerate(siblings):
            w.order = (i + 1) * 10


def _renumber_order_activities(activities: list[Activity]) -> None:
    groups: dict[str, list[Activity]] = defaultdict(list)
    for a in activities:
        groups[a.work_id].append(a)
    for siblings in groups.values():
        for i, a in enumerate(siblings):
            a.order = (i + 1) * 10


def _atomic_write_tsv(path: Path, cols: list[str], rows: Iterable[dict[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else str(r[c])) for c in cols})
    os.replace(tmp, path)


def _rewrite_works(path: Path, works: list[Work]) -> None:
    rows = [
        {
            "id": w.id,
            "parent_id": w.parent_id or "",
            "order": w.order,
            "name": w.name,
        }
        for w in works
    ]
    _atomic_write_tsv(path, WORKS_COLS, rows)


def _rewrite_activities(path: Path, activities: list[Activity]) -> None:
    rows = [
        {
            "id": a.id,
            "work_id": a.work_id,
            "order": a.order,
            "name": a.name,
            "duration": a.duration,
            "predecessors": a.predecessors_raw,
            "status": a.status,
        }
        for a in activities
    ]
    _atomic_write_tsv(path, ACTIVITIES_COLS, rows)


def resolve_project_dir(path: str | Path) -> Path:
    """Accept a directory or a .tsv/.toml file inside the dir."""
    p = Path(path)
    if p.is_dir():
        return p
    if p.is_file():
        return p.parent
    raise LoadError(f"not found: {p}")


def load_project(project_path: str | Path, rewrite_order: bool = False) -> Project:
    pdir = resolve_project_dir(project_path)
    meta = _load_meta(pdir / "project.toml")
    work_rows = _read_tsv(pdir / "works.tsv", WORKS_COLS)
    act_rows = _read_tsv(pdir / "activities.tsv", ACTIVITIES_COLS)

    works = _build_works(work_rows)
    activities = _build_activities(act_rows)

    _assign_missing_ids_works(works)
    _assign_missing_ids_activities(activities)
    _renumber_order_works(works)
    _renumber_order_activities(activities)

    # Parse predecessors DSL once IDs are settled
    for a in activities:
        try:
            a.depends_on = parse_predecessors(a.predecessors_raw)
        except DSLError as e:
            raise LoadError(f"activity {a.id or a.name}: {e}") from e

    if rewrite_order:
        _rewrite_works(pdir / "works.tsv", works)
        _rewrite_activities(pdir / "activities.tsv", activities)

    # Optional WBS dictionary
    dict_path = pdir / "wbs-dictionary.md"
    dictionary_md: Optional[str] = None
    if dict_path.exists():
        dictionary_md = dict_path.read_text(encoding="utf-8")

    return Project(
        meta=meta,
        works=works,
        activities=activities,
        dictionary_md=dictionary_md,
    )

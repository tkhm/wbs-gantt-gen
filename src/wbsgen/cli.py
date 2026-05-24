"""wbsgen CLI (v2): build / check / init.

Project layout expected:
  <project_dir>/
      project.toml
      works.tsv
      activities.tsv

Examples
--------
  wbsgen check examples/generic-software-project
  wbsgen build examples/generic-software-project -o /tmp/wbs-out
  wbsgen build examples/generic-software-project --rewrite-order
  wbsgen build examples/generic-software-project -o /tmp/wbs-out --watch
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from wbsgen import __version__
from wbsgen.bizcal import WorkdayCalendar
from wbsgen.loader import LoadError, load_project, resolve_project_dir
from wbsgen.model import Project
from wbsgen.render.markdown import render_markdown
from wbsgen.scheduler import ScheduleError, critical_path, schedule
from wbsgen.validator import validate


def _make_calendar(project: Project) -> Optional[WorkdayCalendar]:
    if project.meta.start is None:
        return None
    return WorkdayCalendar(project.meta.start, project.meta.calendar)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _build_once(project_dir: Path, out_dir: Path, rewrite_order: bool) -> int:
    try:
        project = load_project(project_dir, rewrite_order=rewrite_order)
    except LoadError as e:
        print(f"load error: {e}", file=sys.stderr)
        return 2

    result = validate(project)
    if result.errors or result.warnings:
        print(result.format(), file=sys.stderr)
    if not result.ok:
        print(f"\n{len(result.errors)} error(s); aborting build.", file=sys.stderr)
        return 1

    calendar = _make_calendar(project)
    try:
        schedule(project, calendar)
    except ScheduleError as e:
        print(f"schedule error: {e}", file=sys.stderr)
        return 1

    md = render_markdown(project, calendar)
    _atomic_write(out_dir / "wbs.md", md)

    cp = critical_path(project)
    units = "営業日" if project.meta.units == "business_days" else "暦日"
    print(
        f"built: {out_dir/'wbs.md'} "
        f"({project.project_duration} {units} 全長, CP {len(cp)} 活動)"
    )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    if args.watch and args.rewrite_order:
        print(
            "--watch と --rewrite-order は併用できません "
            "(rewrite による書き戻しが watch ループを引き起こすため)",
            file=sys.stderr,
        )
        return 2
    project_dir = resolve_project_dir(args.input)
    out_dir = Path(args.output) if args.output else project_dir / "build"
    if args.watch:
        return _watch_loop(project_dir, out_dir, args.rewrite_order)
    return _build_once(project_dir, out_dir, args.rewrite_order)


def cmd_check(args: argparse.Namespace) -> int:
    try:
        project_dir = resolve_project_dir(args.input)
        project = load_project(project_dir)
    except LoadError as e:
        print(f"load error: {e}", file=sys.stderr)
        return 2

    result = validate(project)
    if result.errors or result.warnings:
        print(result.format())
    if not result.ok:
        print(f"\n{len(result.errors)} error(s).", file=sys.stderr)
        return 1

    calendar = _make_calendar(project)
    try:
        schedule(project, calendar)
    except ScheduleError as e:
        print(f"schedule error: {e}", file=sys.stderr)
        return 1

    print(
        f"OK: {len(project.activities)} activities, "
        f"{len(project.works)} works, "
        f"{len(result.warnings)} warning(s)."
    )
    return 0


_INIT_PROJECT_TOML = """\
# wbsgen project metadata
# 詳細は README の「project.toml の書き方」を参照
[project]
name = "新規プロジェクト"
description = ""
start = 2026-06-01            # 任意。未指定なら Day N 表示
units = "business_days"       # business_days | calendar_days
near_critical_threshold = 2   # 0 < TF <= 閾値 を near-critical と判定

[project.calendar]
working_days = ["mon", "tue", "wed", "thu", "fri"]
holidays_preset = "jp"        # "jp" (jpholiday) | "none"
# holidays = ["2026-08-12"]   # プロジェクト固有の追加休日
"""

# 雛形 WBS: L1 (フェーズ) → L2 (ワークパッケージ) の最小構成。
# WP は「成果物名」で命名するのが PMBOK 的に標準。
_INIT_WORKS_TSV = (
    "id\tparent_id\torder\tname\n"
    "w-phase1\t\t\tフェーズ1\n"
    "w-phase1-output\tw-phase1\t\t成果物1\n"
    "w-phase2\t\t\tフェーズ2\n"
    "w-phase2-output\tw-phase2\t\t成果物2\n"
)

# 雛形 activities: 各 WP に紐づく作業。依存は FS のみで十分な場合がほとんど。
_INIT_ACTIVITIES_TSV = (
    "work_id\tid\torder\tname\tduration\tpredecessors\tstatus\n"
    "w-phase1-output\ta-task1\t\tタスク1\t3\t\ttodo\n"
    "w-phase2-output\ta-task2\t\tタスク2\t5\ta-task1\ttodo\n"
    "w-phase2-output\ta-m-end\t\t完了\t0\ta-task2\ttodo\n"
)

# 雛形 WBS辞書: 任意。各 WP の補足を書く場所
_INIT_WBS_DICTIONARY_MD = """\
# WBS 辞書

各ワークパッケージ (WP = WBS の最下層) の補足説明を書く。
受入基準・前提・責任者・リスク・参考資料など、TSV に収まらない情報をここに。
このファイルがあれば build 時に wbs.md の「WBS 辞書」セクションとして取り込まれる。
不要なら削除して構わない (なくても build は動く)。

## 1.1 (w-phase1-output) 成果物1

- **受入基準**:
- **責任者**:
- **前提**:

## 2.1 (w-phase2-output) 成果物2

- **受入基準**:
- **責任者**:
"""


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.dir)
    if target.exists() and any(target.iterdir()):
        print(f"refusing to write into non-empty directory {target}", file=sys.stderr)
        return 1
    target.mkdir(parents=True, exist_ok=True)
    (target / "project.toml").write_text(_INIT_PROJECT_TOML, encoding="utf-8")
    (target / "works.tsv").write_text(_INIT_WORKS_TSV, encoding="utf-8")
    (target / "activities.tsv").write_text(_INIT_ACTIVITIES_TSV, encoding="utf-8")
    (target / "wbs-dictionary.md").write_text(_INIT_WBS_DICTIONARY_MD, encoding="utf-8")
    print(
        f"created {target}/{{project.toml, works.tsv, activities.tsv, wbs-dictionary.md}}"
    )
    print(
        f"  edit those files then run: wbsgen build {target} --watch"
    )
    return 0


_WATCH_TARGETS = {
    "project.toml",
    "works.tsv",
    "activities.tsv",
    "wbs-dictionary.md",
}


def _watch_loop(project_dir: Path, out_dir: Path, rewrite_order: bool) -> int:
    """Watch the project directory and rebuild on source changes.

    ファイル単独パスを watch すると、エディタの atomic save (tmp 作成 →
    rename) で inode が変わってイベントを取りこぼす。ここではディレクトリ
    全体を監視し、watch_filter で対象 3 ファイル名に絞る。
    """
    try:
        from watchfiles import watch
    except ImportError:
        print(
            "watchfiles is required for --watch (pip install watchfiles)",
            file=sys.stderr,
        )
        return 2

    target_dir = project_dir.resolve()

    def _is_source(_change, path: str) -> bool:
        return Path(path).name in _WATCH_TARGETS

    print(
        f"watching {target_dir}/ "
        f"({', '.join(sorted(_WATCH_TARGETS))}) ... Ctrl+C to exit"
    )
    rc = _build_once(project_dir, out_dir, rewrite_order)
    if rc != 0:
        print("(initial build had errors; will retry on save)")
    try:
        for _changes in watch(str(target_dir), watch_filter=_is_source):
            print()
            _build_once(project_dir, out_dir, rewrite_order)
            print()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wbsgen",
        description="PMBOK-aligned WBS / Gantt generator (CPM, TSV source).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="generate Markdown from TSV project")
    p_build.add_argument("input", help="project directory (or any file inside it)")
    p_build.add_argument(
        "-o",
        "--output",
        default=None,
        help="output directory (default: <project_dir>/build/)",
    )
    p_build.add_argument("--watch", action="store_true", help="rebuild on file changes")
    p_build.add_argument(
        "--rewrite-order",
        action="store_true",
        help="renumber order columns and fill in blank ids back to the TSV files",
    )
    p_build.set_defaults(func=cmd_build)

    p_check = sub.add_parser("check", help="validate only; no output files written")
    p_check.add_argument("input", help="project directory")
    p_check.set_defaults(func=cmd_check)

    p_init = sub.add_parser("init", help="create a starter project skeleton in <dir>")
    p_init.add_argument("dir", help="target directory (must be empty or not exist)")
    p_init.set_defaults(func=cmd_init)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

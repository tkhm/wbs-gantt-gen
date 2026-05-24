from pathlib import Path

import pytest

from wbsgen.loader import LoadError, load_project


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_load_generic_example():
    p = load_project(EXAMPLES / "generic-software-project")
    assert p.meta.name == "新サービス α リリース"
    assert len(p.works) == 33  # L1 + L2 + L3 まで
    assert len(p.activities) == 17


def test_load_dogfood_example():
    p = load_project(EXAMPLES / "dogfood-wbs-gantt-gen")
    assert p.meta.name.startswith("wbsgen")
    assert any(a.status == "done" for a in p.activities)


def test_blank_id_auto_assigned(tmp_path: Path):
    (tmp_path / "project.toml").write_text(
        "[project]\nname = 't'\nstart = 2026-06-01\n", encoding="utf-8"
    )
    (tmp_path / "works.tsv").write_text(
        "id\tparent_id\torder\tname\n\t\t\tAlpha\n", encoding="utf-8"
    )
    (tmp_path / "activities.tsv").write_text(
        "work_id\tid\torder\tname\tduration\tpredecessors\tstatus\n"
        "w-alpha\t\t\tTask One\t3\t\ttodo\n",
        encoding="utf-8",
    )
    p = load_project(tmp_path)
    assert p.works[0].id == "w-alpha"
    assert p.activities[0].id == "a-task-one"
    assert p.activities[0].work_id == "w-alpha"


def test_order_renumbered_to_10_step(tmp_path: Path):
    (tmp_path / "project.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (tmp_path / "works.tsv").write_text(
        "id\tparent_id\torder\tname\n"
        "w-a\t\t100\tA\n"
        "w-b\t\t50\tB\n",
        encoding="utf-8",
    )
    (tmp_path / "activities.tsv").write_text(
        "work_id\tid\torder\tname\tduration\tpredecessors\tstatus\n"
        "w-a\ta-x\t\tX\t1\t\ttodo\n",
        encoding="utf-8",
    )
    p = load_project(tmp_path)
    # Row order wins: w-a is first, w-b is second.
    assert [w.id for w in p.works] == ["w-a", "w-b"]
    assert [w.order for w in p.works] == [10, 20]


def test_missing_required_column(tmp_path: Path):
    (tmp_path / "project.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (tmp_path / "works.tsv").write_text("id\tparent_id\torder\tname\n", encoding="utf-8")
    (tmp_path / "activities.tsv").write_text(
        # Missing duration → LoadError
        "work_id\tid\torder\tname\tpredecessors\tstatus\n"
        "w-a\ta-x\t\tX\t\ttodo\n",
        encoding="utf-8",
    )
    with pytest.raises(LoadError):
        load_project(tmp_path)


def test_predecessors_dsl_parsed_after_id_assignment(tmp_path: Path):
    (tmp_path / "project.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (tmp_path / "works.tsv").write_text(
        "id\tparent_id\torder\tname\nw-p\t\t\tP\n", encoding="utf-8"
    )
    (tmp_path / "activities.tsv").write_text(
        "work_id\tid\torder\tname\tduration\tpredecessors\tstatus\n"
        "w-p\ta-one\t\tOne\t2\t\ttodo\n"
        "w-p\ta-two\t\tTwo\t3\ta-one+2\ttodo\n",
        encoding="utf-8",
    )
    p = load_project(tmp_path)
    two = next(a for a in p.activities if a.id == "a-two")
    assert len(two.depends_on) == 1
    assert two.depends_on[0].predecessor_id == "a-one"
    assert two.depends_on[0].lag == 2


def test_rewrite_order_persists(tmp_path: Path):
    (tmp_path / "project.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    works_path = tmp_path / "works.tsv"
    works_path.write_text(
        "id\tparent_id\torder\tname\n"
        "\t\t\tFirst\n"
        "\t\t\tSecond\n",
        encoding="utf-8",
    )
    (tmp_path / "activities.tsv").write_text(
        "work_id\tid\torder\tname\tduration\tpredecessors\tstatus\nw-first\tx\t\tT\t1\t\ttodo\n",
        encoding="utf-8",
    )
    load_project(tmp_path, rewrite_order=True)
    content = works_path.read_text(encoding="utf-8")
    assert "w-first" in content
    assert "w-second" in content
    # Order should be 10/20 after rewrite.
    lines = content.strip().splitlines()
    assert lines[1].split("\t")[2] == "10"
    assert lines[2].split("\t")[2] == "20"


def test_wbs_dictionary_loaded_when_present(tmp_path: Path):
    (tmp_path / "project.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (tmp_path / "works.tsv").write_text(
        "id\tparent_id\torder\tname\nw-a\t\t\tA\n", encoding="utf-8"
    )
    (tmp_path / "activities.tsv").write_text(
        "work_id\tid\torder\tname\tduration\tpredecessors\tstatus\nw-a\ta-x\t\tX\t1\t\ttodo\n",
        encoding="utf-8",
    )
    (tmp_path / "wbs-dictionary.md").write_text(
        "# 辞書\n\n## A について\n受入基準: 完成すること\n", encoding="utf-8"
    )
    p = load_project(tmp_path)
    assert p.dictionary_md is not None
    assert "A について" in p.dictionary_md


def test_wbs_dictionary_absent_is_none(tmp_path: Path):
    (tmp_path / "project.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (tmp_path / "works.tsv").write_text(
        "id\tparent_id\torder\tname\nw-a\t\t\tA\n", encoding="utf-8"
    )
    (tmp_path / "activities.tsv").write_text(
        "work_id\tid\torder\tname\tduration\tpredecessors\tstatus\nw-a\ta-x\t\tX\t1\t\ttodo\n",
        encoding="utf-8",
    )
    p = load_project(tmp_path)
    assert p.dictionary_md is None

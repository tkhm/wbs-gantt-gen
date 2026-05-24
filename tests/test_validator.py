from wbsgen.model import Activity, Dependency, Project, ProjectMeta, Work
from wbsgen.validator import validate


def _proj(activities, works=None):
    return Project(meta=ProjectMeta(), works=works or [], activities=activities)


def test_duplicate_id_across_works_and_activities():
    p = _proj(
        activities=[Activity(id="x", name="a", work_id="x")],
        works=[Work(id="x", name="w")],
    )
    r = validate(p)
    assert not r.ok
    assert any("duplicate id" in e.message for e in r.errors)


def test_self_dependency():
    p = _proj(
        [Activity(id="a-a", name="a", work_id="w-a", depends_on=[Dependency("a-a")])],
        works=[Work(id="w-a", name="W")],
    )
    r = validate(p)
    assert any("depends on itself" in e.message for e in r.errors)


def test_undefined_predecessor():
    p = _proj(
        [Activity(id="a-a", name="a", work_id="w-a", depends_on=[Dependency("a-ghost")])],
        works=[Work(id="w-a", name="W")],
    )
    r = validate(p)
    assert any("predecessor 'a-ghost' not found" in e.message for e in r.errors)


def test_unresolved_work_id():
    p = _proj([Activity(id="a-a", name="a", work_id="w-missing")])
    r = validate(p)
    assert any("work_id 'w-missing' not found" in e.message for e in r.errors)


def test_dependency_cycle_detected():
    p = _proj(
        [
            Activity(id="a-a", name="A", work_id="w", depends_on=[Dependency("a-b")]),
            Activity(id="a-b", name="B", work_id="w", depends_on=[Dependency("a-c")]),
            Activity(id="a-c", name="C", work_id="w", depends_on=[Dependency("a-a")]),
        ],
        works=[Work(id="w", name="W")],
    )
    r = validate(p)
    assert any("dependency cycle" in e.message for e in r.errors)


def test_negative_duration():
    p = _proj(
        [Activity(id="a-x", name="X", work_id="w", duration=-1)],
        works=[Work(id="w", name="W")],
    )
    r = validate(p)
    assert any("negative duration" in e.message for e in r.errors)


def test_work_parent_unresolved():
    p = _proj([], works=[Work(id="w-a", name="A", parent_id="w-ghost")])
    r = validate(p)
    assert any("parent_id 'w-ghost' not found" in e.message for e in r.errors)


def test_milestone_no_successor_warning():
    p = _proj(
        [Activity(id="a-m", name="M", work_id="w", duration=0)],
        works=[Work(id="w", name="W")],
    )
    r = validate(p)
    assert any("milestone" in w.message and "no successor" in w.message for w in r.warnings)

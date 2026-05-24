from wbsgen.model import Project, ProjectMeta, Work
from wbsgen.wbscode import compute_wbs_codes


def _proj(works):
    return Project(meta=ProjectMeta(), works=works)


def test_top_level_order():
    p = _proj([
        Work(id="w-a", name="A", parent_id=None, order=10),
        Work(id="w-b", name="B", parent_id=None, order=20),
    ])
    codes = compute_wbs_codes(p)
    assert codes["w-a"] == "1"
    assert codes["w-b"] == "2"


def test_nested():
    p = _proj([
        Work(id="w-a", name="A", parent_id=None, order=10),
        Work(id="w-a1", name="A1", parent_id="w-a", order=10),
        Work(id="w-a2", name="A2", parent_id="w-a", order=20),
        Work(id="w-b", name="B", parent_id=None, order=20),
    ])
    codes = compute_wbs_codes(p)
    assert codes["w-a"] == "1"
    assert codes["w-a1"] == "1.1"
    assert codes["w-a2"] == "1.2"
    assert codes["w-b"] == "2"


def test_order_is_authoritative_not_id():
    # Verify order overrides id-alphabetical: w-z first because order=5
    p = _proj([
        Work(id="w-z", name="Z", parent_id=None, order=5),
        Work(id="w-a", name="A", parent_id=None, order=10),
    ])
    codes = compute_wbs_codes(p)
    assert codes["w-z"] == "1"
    assert codes["w-a"] == "2"

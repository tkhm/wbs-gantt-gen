import pytest

from wbsgen.deps_dsl import DSLError, format_predecessors, parse_predecessors
from wbsgen.model import Dependency


def test_empty_returns_empty():
    assert parse_predecessors("") == []
    assert parse_predecessors("   ") == []
    assert parse_predecessors(None) == []  # type: ignore[arg-type]


def test_simple_fs_short_form():
    deps = parse_predecessors("a-foo")
    assert deps == [Dependency("a-foo", "FS", 0)]


def test_multiple_short_form():
    deps = parse_predecessors("a-foo, a-bar")
    assert [d.predecessor_id for d in deps] == ["a-foo", "a-bar"]
    assert all(d.type == "FS" and d.lag == 0 for d in deps)


def test_lag_positive():
    [d] = parse_predecessors("a-foo+2")
    assert d.predecessor_id == "a-foo" and d.type == "FS" and d.lag == 2


def test_lag_negative():
    [d] = parse_predecessors("a-foo-3")
    assert d.lag == -3


def test_type_only():
    [d] = parse_predecessors("a-foo/SS")
    assert d.type == "SS" and d.lag == 0


def test_type_then_lag():
    [d] = parse_predecessors("a-foo/FF-1")
    assert d.type == "FF" and d.lag == -1


def test_lag_then_type():
    [d] = parse_predecessors("a-foo+2/SS")
    assert d.type == "SS" and d.lag == 2


def test_case_insensitive_type():
    [d] = parse_predecessors("a-foo/ss")
    assert d.type == "SS"


def test_invalid_entry_raises():
    with pytest.raises(DSLError):
        parse_predecessors("a-foo/XX")
    with pytest.raises(DSLError):
        parse_predecessors("@bad@")


def test_round_trip_format():
    raw = "a-foo, a-bar+2, a-baz/SS, a-qux/FF-1"
    deps = parse_predecessors(raw)
    assert format_predecessors(deps) == "a-foo, a-bar+2, a-baz/SS, a-qux/FF-1"


def test_dotted_id_simple():
    [d] = parse_predecessors("1.1-a1")
    assert d.predecessor_id == "1.1-a1" and d.type == "FS" and d.lag == 0


def test_dotted_id_with_lag():
    [d] = parse_predecessors("1.1-a1+2")
    assert d.predecessor_id == "1.1-a1" and d.lag == 2


def test_dotted_id_with_type():
    [d] = parse_predecessors("1.1-a1/SS")
    assert d.predecessor_id == "1.1-a1" and d.type == "SS"


def test_pure_numeric_dotted_id():
    [d] = parse_predecessors("1.1.1")
    assert d.predecessor_id == "1.1.1"

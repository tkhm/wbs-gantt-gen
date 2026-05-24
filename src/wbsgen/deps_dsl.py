"""predecessors DSL parser and serializer.

Grammar
-------
predecessors  := entry ("," entry)*
entry         := id [ "/" type ] [ ( "+" | "-" ) digits ]
                | id [ ( "+" | "-" ) digits ] [ "/" type ]
id            := [A-Za-z0-9._-]+   ← ドットも許容 (例: "1.1-a1", "1.1.1")
type          := "FS" | "SS" | "FF" | "SF"   (case-insensitive)
digits        := [0-9]+

Examples:
  a-foo                     → FS, lag 0
  a-foo+2                   → FS, lag +2
  a-bar-1                   → FS, lag -1
  a-baz/SS                  → SS, lag 0
  a-qux/FF-1                → FF, lag -1
  a-foo/SS+3, a-bar         → [(a-foo, SS, +3), (a-bar, FS, 0)]
"""

from __future__ import annotations

import re

from wbsgen.model import Dependency, DependencyType


# Entry: capture id, optional /TYPE, optional +/-LAG. Order of type and lag
# is flexible: both `a-id/SS+2` and `a-id+2/SS` accepted.
_ENTRY_RE = re.compile(
    r"""^\s*
    (?P<id>[A-Za-z0-9._-]+?)
    (?:
        (?:/(?P<type1>FS|SS|FF|SF))?
        (?:(?P<sign1>[+-])(?P<lag1>\d+))?
    )
    (?:
        (?:(?P<sign2>[+-])(?P<lag2>\d+))?
        (?:/(?P<type2>FS|SS|FF|SF))?
    )
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


class DSLError(ValueError):
    pass


def parse_predecessors(raw: str) -> list[Dependency]:
    """Parse a DSL string into a list of Dependency.

    Empty/whitespace input returns []. Errors are raised as DSLError
    with the offending entry quoted.
    """
    if raw is None:
        return []
    raw = raw.strip()
    if not raw:
        return []
    entries = [e for e in (s.strip() for s in raw.split(",")) if e]
    out: list[Dependency] = []
    for ent in entries:
        m = _ENTRY_RE.match(ent)
        if not m:
            raise DSLError(f"invalid predecessor entry: {ent!r}")
        pred_id = m.group("id")
        type_str = m.group("type1") or m.group("type2") or "FS"
        sign = m.group("sign1") or m.group("sign2")
        lag_str = m.group("lag1") or m.group("lag2")
        if sign and not lag_str:
            raise DSLError(f"invalid lag in entry: {ent!r}")
        lag = 0
        if lag_str:
            lag = int(lag_str)
            if sign == "-":
                lag = -lag
        out.append(
            Dependency(
                predecessor_id=pred_id,
                type=type_str.upper(),  # type: ignore[arg-type]
                lag=lag,
            )
        )
    return out


def format_predecessors(deps: list[Dependency]) -> str:
    """Inverse of parse: render a Dependency list as a DSL string."""
    parts: list[str] = []
    for d in deps:
        s = d.predecessor_id
        if d.type != "FS":
            s += f"/{d.type}"
        if d.lag != 0:
            s += f"{d.lag:+d}"
        parts.append(s)
    return ", ".join(parts)

"""Shared rendering helpers."""

from __future__ import annotations

import re

_SAFE_TAG = re.compile(r"[^A-Za-z0-9_]")


def safe_mermaid_id(s: str) -> str:
    """Mermaid-safe node id: alphanumeric + underscore only, must start with a letter."""
    out = _SAFE_TAG.sub("_", s)
    if not out:
        out = "x"
    if out[0].isdigit():
        out = "n_" + out
    return out


def mermaid_escape_label(s: str) -> str:
    """Escape characters that break Mermaid node labels."""
    return s.replace('"', "&quot;").replace("\n", " ")

"""ID generation utilities.

Rules:
- Slugify name (ASCII; for Japanese names use unicodedata + fallback)
- Apply prefix (`w-` for Work, `a-` for Activity)
- Append `-2`, `-3`, ... on collision against existing IDs.

For Japanese names, slugify produces a romanized fallback by stripping
non-ASCII, but if the result is empty it falls back to a content-hash
suffix (`w-x-abc123`).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_INVALID = re.compile(r"[^a-z0-9-]+")
_DASHES = re.compile(r"-+")


def _slug_core(text: str) -> str:
    """Normalize and slugify; returns empty string if nothing usable."""
    # Normalize unicode (NFKD): "ＡＰＩ" → "API", "ｱｲｳ" → "アイウ"
    nfkd = unicodedata.normalize("NFKD", text)
    # Strip combining marks (accents)
    ascii_part = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    # Drop non-ASCII (Japanese kanji/kana etc.)
    ascii_only = "".join(ch if ord(ch) < 128 else " " for ch in ascii_part)
    lowered = ascii_only.lower()
    cleaned = _INVALID.sub("-", lowered)
    cleaned = _DASHES.sub("-", cleaned).strip("-")
    return cleaned


def slugify(text: str, prefix: str) -> str:
    """Produce a base ID `{prefix}-{slug}` from human text.

    If `text` has no ASCII content (e.g., pure Japanese), produces
    `{prefix}-x-{6-char hash}` as a deterministic fallback.
    """
    if not prefix.endswith("-"):
        prefix = prefix + "-"
    core = _slug_core(text)
    if not core:
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
        return f"{prefix}x-{h}"
    return f"{prefix}{core}"


def unique_id(base: str, existing: set[str]) -> str:
    """Return `base`, or `base-2`, `base-3`, ... if base is taken."""
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def assign_id(name: str, prefix: str, existing: set[str]) -> str:
    """Generate a unique id from `name` with collision avoidance."""
    return unique_id(slugify(name, prefix), existing)

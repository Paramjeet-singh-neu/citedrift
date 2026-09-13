"""Jaccard over sets. Empty union is undefined (null + note)."""

from __future__ import annotations


def jaccard(a: set[str], b: set[str]) -> tuple[float | None, str | None]:
    if not a and not b:
        return None, "both_empty"
    union = a | b
    if not union:
        return None, "union_empty"
    return len(a & b) / len(union), None

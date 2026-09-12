"""Keep the titled citation list. Inline lists are doubled; expanded are not."""

from __future__ import annotations

from typing import Any


def keep_references(refs: list[Any], delivery_mode: str) -> list[dict[str, Any]]:
    cleaned = [r for r in refs if isinstance(r, dict)]
    if delivery_mode == "expanded":
        return cleaned
    n = len(cleaned)
    if n >= 2 and n % 2 == 0:
        half = n // 2
        first, second = cleaned[:half], cleaned[half:]
        first_untitled = all(not r.get("title") for r in first)
        second_titled = all(bool(r.get("title")) for r in second)
        links_match = all(first[i].get("link") == second[i].get("link") for i in range(half))
        if first_untitled and second_titled and links_match:
            return second
    titled = [r for r in cleaned if r.get("title")]
    return titled if titled else cleaned

"""Rank-biased overlap with extrapolation (Webber, Moffat, Zobel 2010, eq. 32)."""

from __future__ import annotations

P = 0.9


def unique_preserve(seq: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in seq:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def prefix_overlaps(a: list[str], b: list[str]) -> list[int]:
    seen_a: set[str] = set()
    seen_b: set[str] = set()
    overlap = 0
    out: list[int] = []
    n = max(len(a), len(b))
    for i in range(n):
        if i < len(a):
            item = a[i]
            if item in seen_b:
                overlap += 1
            seen_a.add(item)
        if i < len(b):
            item = b[i]
            if item in seen_a:
                overlap += 1
            seen_b.add(item)
        out.append(overlap)
    return out


def rbo(list1: list[str], list2: list[str], p: float = P) -> tuple[float | None, str | None]:
    a = unique_preserve(list1)
    b = unique_preserve(list2)
    if not a and not b:
        return None, "both_empty"
    if not a or not b:
        return 0.0, None
    if len(a) > len(b):
        a, b = b, a
    s = len(a)
    ell = len(b)
    overlaps = prefix_overlaps(a, b)
    x_s = overlaps[s - 1]
    x_l = overlaps[ell - 1]
    sum1 = 0.0
    for d in range(1, ell + 1):
        sum1 += (p**d) * (overlaps[d - 1] / d)
    sum2 = 0.0
    for d in range(s + 1, ell + 1):
        sum2 += (p**d) * x_s * (d - s) / (s * d)
    term1 = ((1 - p) / p) * (sum1 + sum2)
    term2 = (p**ell) * ((x_l - x_s) / ell + x_s / s)
    return term1 + term2, None

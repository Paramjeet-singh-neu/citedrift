"""Inline SVG charts. No network, no animation, no gradients."""

from __future__ import annotations

import html
from typing import Any

CLASS_COLORS: dict[str, str] = {
    "academic": "#2c3e50",
    "advocacy": "#1e8449",
    "clinical_reference": "#148f77",
    "commerce": "#6c3483",
    "consumer_health": "#d35400",
    "gov_health": "#1a5276",
    "health_system": "#1abc9c",
    "manufacturer": "#922b21",
    "professional_society": "#5d6d7e",
    "social": "#2471a3",
    "unclassified": "#7f8c8d",
    "video": "#c0392b",
}

FALLBACK_COLORS = ("#34495e", "#7d3c98", "#117a65", "#b7950b", "#633974")

SEGMENT_COLORS = {
    "complete": "#1a5276",
    "genuine_absence": "#7f8c8d",
    "failed_fetch": "#922b21",
    "inline": "#1a5276",
    "expanded": "#d35400",
    "none": "#7f8c8d",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def color_for(name: str, used: dict[str, str]) -> str:
    if name in used:
        return used[name]
    if name in CLASS_COLORS:
        used[name] = CLASS_COLORS[name]
        return used[name]
    used[name] = FALLBACK_COLORS[len(used) % len(FALLBACK_COLORS)]
    return used[name]


def _legend(items: list[tuple[str, str]], x: float, y: float) -> str:
    parts: list[str] = []
    for i, (label, fill) in enumerate(items):
        yy = y + i * 16
        parts.append(
            f'<rect x="{x:.1f}" y="{yy:.1f}" width="10" height="10" fill="{fill}"/>'
            f'<text x="{x + 16:.1f}" y="{yy + 9:.1f}" font-size="11" fill="#222">'
            f"{esc(label)}</text>"
        )
    return "".join(parts)


def stacked_percent(
    rows: list[tuple[str, int, dict[str, int]]],
    *,
    title: str,
    n: int,
) -> str:
    """100% stacked bars. Each row is (category, n_category, class -> count)."""
    classes: list[str] = []
    seen: set[str] = set()
    for _name, _n, counts in rows:
        for key in counts:
            if key not in seen:
                seen.add(key)
                classes.append(key)
    classes.sort()
    palette: dict[str, str] = {}
    for name in classes:
        color_for(name, palette)

    width, height = 760, 340
    left, right, top, bottom = 56, 200, 36, 56
    plot_w = width - left - right
    plot_h = height - top - bottom
    n_cat = max(len(rows), 1)
    gap = 12
    bar_w = max(12.0, (plot_w - gap * n_cat) / n_cat)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img">',
        f"<title>{esc(title)} (n={n})</title>",
        f'<text x="{left}" y="20" font-size="13" font-weight="600" fill="#222">'
        f"{esc(title)}  n={n}</text>",
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" '
        f'stroke="#444" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" stroke="#444" stroke-width="1"/>',
        f'<text x="{12}" y="{top + 8}" font-size="10" fill="#444">100%</text>',
        f'<text x="{18}" y="{top + plot_h}" font-size="10" fill="#444">0%</text>',
    ]
    for i, (cat, n_cat_row, counts) in enumerate(rows):
        x = left + i * (bar_w + gap) + gap / 2
        total = sum(counts.values()) or 1
        y = top + plot_h
        for cls in classes:
            c = counts.get(cls, 0)
            if c <= 0:
                continue
            h = plot_h * (c / total)
            y -= h
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                f'fill="{palette[cls]}" stroke="#fff" stroke-width="0.5"/>'
            )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + plot_h + 14:.1f}" '
            f'font-size="10" fill="#222" text-anchor="middle">{esc(cat)}</text>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + plot_h + 26:.1f}" '
            f'font-size="9" fill="#555" text-anchor="middle">n={n_cat_row}</text>'
        )
    legend = [(cls, palette[cls]) for cls in classes]
    parts.append(_legend(legend, width - right + 12, top))
    parts.append("</svg>")
    return "".join(parts)


def stacked_counts(
    rows: list[tuple[str, list[tuple[str, int]]]],
    *,
    title: str,
    n: int,
    y_max: int,
) -> str:
    """Stacked count bars. Each row is (category, [(segment, count), ...])."""
    width, height = 760, 360
    left, right, top, bottom = 48, 140, 36, 72
    plot_w = width - left - right
    plot_h = height - top - bottom
    n_cat = max(len(rows), 1)
    gap = 8
    bar_w = max(8.0, (plot_w - gap * n_cat) / n_cat)
    ymax = max(y_max, 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img">',
        f"<title>{esc(title)} (n={n})</title>",
        f'<text x="{left}" y="20" font-size="13" font-weight="600" fill="#222">'
        f"{esc(title)}  n={n}</text>",
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" '
        f'stroke="#444" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" stroke="#444" stroke-width="1"/>',
        f'<text x="8" y="{top + 8}" font-size="10" fill="#444">{ymax}</text>',
        f'<text x="16" y="{top + plot_h}" font-size="10" fill="#444">0</text>',
    ]
    legend_items: list[tuple[str, str]] = []
    seen_seg: set[str] = set()
    for i, (cat, segs) in enumerate(rows):
        x = left + i * (bar_w + gap) + gap / 2
        y = top + plot_h
        for name, count in segs:
            if count <= 0:
                continue
            if name not in seen_seg:
                seen_seg.add(name)
                legend_items.append((name, SEGMENT_COLORS.get(name, "#555")))
            h = plot_h * (count / ymax)
            y -= h
            fill = SEGMENT_COLORS.get(name, "#555")
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                f'fill="{fill}" stroke="#fff" stroke-width="0.4"/>'
            )
        label_y = top + plot_h + 12
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{label_y:.1f}" font-size="9" '
            f'fill="#222" text-anchor="end" transform="rotate(-55 '
            f'{x + bar_w / 2:.1f} {label_y:.1f})">{esc(cat)}</text>'
        )
    parts.append(_legend(legend_items, width - right + 8, top))
    parts.append("</svg>")
    return "".join(parts)


def grouped_counts(
    groups: list[tuple[str, dict[str, int]]],
    series: list[str],
    *,
    title: str,
    n: int,
) -> str:
    width, height = 640, 300
    left, right, top, bottom = 48, 140, 36, 40
    plot_w = width - left - right
    plot_h = height - top - bottom
    n_g = max(len(groups), 1)
    n_s = max(len(series), 1)
    group_w = plot_w / n_g
    bar_w = min(28.0, (group_w - 20) / n_s)
    ymax = 1
    for _name, counts in groups:
        ymax = max(ymax, max(counts.values(), default=0))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img">',
        f"<title>{esc(title)} (n={n})</title>",
        f'<text x="{left}" y="20" font-size="13" font-weight="600" fill="#222">'
        f"{esc(title)}  n={n}</text>",
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" '
        f'stroke="#444" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" stroke="#444" stroke-width="1"/>',
        f'<text x="8" y="{top + 8}" font-size="10" fill="#444">{ymax}</text>',
    ]
    for gi, (gname, counts) in enumerate(groups):
        gx = left + gi * group_w + (group_w - bar_w * n_s) / 2
        for si, sname in enumerate(series):
            c = counts.get(sname, 0)
            h = plot_h * (c / ymax) if ymax else 0
            x = gx + si * bar_w
            y = top + plot_h - h
            fill = SEGMENT_COLORS.get(sname, "#555")
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 2:.1f}" '
                f'height="{h:.1f}" fill="{fill}"/>'
            )
        parts.append(
            f'<text x="{left + gi * group_w + group_w / 2:.1f}" '
            f'y="{top + plot_h + 16:.1f}" font-size="11" fill="#222" '
            f'text-anchor="middle">{esc(gname)}</text>'
        )
    parts.append(_legend([(s, SEGMENT_COLORS.get(s, "#555")) for s in series], width - right + 8, top))
    parts.append("</svg>")
    return "".join(parts)

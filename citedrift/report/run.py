"""Build a self-contained report.html from metrics.json. No network."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from citedrift.collect.serpapi import GL, HL, LOCATION
from citedrift.report.svg import grouped_counts, stacked_counts, stacked_percent

ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = ROOT / "data" / "analysis" / "metrics.json"
QUERIES_PATH = ROOT / "config" / "queries.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "collect.yml"
OUT_PATH = ROOT / "report" / "report.html"

STAGE_ORDER = ("symptoms", "diagnosis", "treatment", "branded")
AUDIENCE_ORDER = ("patient", "hcp")
PRESENCE_SEGS = (
    ("complete", "runs_with_complete_aio"),
    ("genuine_absence", "runs_genuine_absence"),
    ("failed_fetch", "runs_failed_fetch"),
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def cadence_cron(path: Path) -> str | None:
    if not path.is_file():
        return None
    match = re.search(r'cron:\s*"([^"]+)"', path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def parse_z(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def collect_times_and_runs(obj: Any) -> tuple[list[str], set[str]]:
    times: list[str] = []
    runs: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                if key in {"fetched_at", "fetched_at_a", "fetched_at_b"} and isinstance(val, str):
                    times.append(val)
                if key in {"run_id", "run_id_a", "run_id_b"} and isinstance(val, str):
                    runs.add(val)
                walk(val)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return times, runs


def fmt_num(value: Any, digits: int = 4) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def fmt_pct(value: Any) -> str:
    if value is None:
        return "null"
    return f"{float(value):.1f}"


def esc(value: Any) -> str:
    from html import escape

    return escape(str(value), quote=True)


def query_meta(queries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(q["id"]): q for q in queries}


def unique_counts(queries: list[dict[str, Any]], field: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    order: list[str] = []
    for q in queries:
        key = str(q.get(field) or "unknown")
        if key not in counts:
            order.append(key)
            counts[key] = 0
        counts[key] += 1
    return [(name, counts[name]) for name in order]


def css() -> str:
    return """
body { margin: 0; padding: 24px; font-family: Helvetica, Arial, sans-serif;
       color: #222; background: #fff; line-height: 1.4; }
main { max-width: 960px; margin: 0 auto; }
h1 { font-size: 22px; font-weight: 700; margin: 0 0 8px; }
h2 { font-size: 18px; font-weight: 700; margin: 32px 0 12px; border-bottom: 1px solid #ccc;
     padding-bottom: 4px; }
h3 { font-size: 15px; font-weight: 700; margin: 20px 0 8px; }
p, li { font-size: 14px; }
.note { color: #444; font-size: 13px; }
table { border-collapse: collapse; margin: 8px 0 16px; font-size: 13px; }
th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; vertical-align: top; }
th { background: #f3f3f3; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
caption { caption-side: top; text-align: left; font-size: 13px; margin-bottom: 4px; color: #333; }
svg { display: block; margin: 8px 0 16px; max-width: 100%; height: auto; }
.meta dt { font-weight: 600; }
.meta dd { margin: 0 0 8px; }
.intro p { margin: 0 0 12px; font-size: 15px; }
""".strip()


def table(headers: list[tuple[str, bool]], rows: list[list[str]], caption: str) -> str:
    head = "".join(
        f'<th class="num">{esc(h)}</th>' if numeric else f"<th>{esc(h)}</th>"
        for h, numeric in headers
    )
    body_rows = []
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cls = ' class="num"' if headers[i][1] else ""
            cells.append(f"<td{cls}>{esc(cell)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f"<table><caption>{esc(caption)}</caption><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


INTRO_LEAD = (
    "This measures which sources Google's AI Overview cites when someone searches a health question, and whether that set of sources stays the same when you ask again."
)
INTRO_TAIL = (
    "Four things stand out in the data so far.",
    "AI Overviews appeared on 59 of 60 attempts. The single genuine absence was on a clinician-phrased query; one further record is a collector-side network timeout, logged separately rather than counted as an absence.",
    "What gets cited first depends on how the question is phrased. Across the top three cited positions, academic sources were 37.5% of citations on clinician-phrased queries and 0 of 150 on patient-phrased ones — academic sources do appear in patient results, 10 times across all positions, but never near the top. Health-system sites were the reverse: 30% of patient top-three citations, and absent from clinician-phrased results at any position. The two phrasings also arrived through different delivery paths, with patient observations returning the AI Overview inline and clinician observations requiring a second fetch.",
    "Being cited and being cited first are different things. YouTube was the most-cited domain in the sample at 68 citations — ahead of Mayo Clinic at 38 and NIH at 33 — but 13 of those 68 appear in the top three. Professional medical societies were cited 15 times and never once in the top three positions of either audience.",
    "Within short intervals, citation sets were almost always identical: 15 of 16 pairs sampled 33–47 minutes apart matched exactly. Across intervals of 8–22 hours, they moved, and unevenly. The two clinician-phrased queries degraded most — one fell from 0.33 to 0.09 Jaccard across successive comparisons, ending with one shared citation in eleven. Branded queries for type 2 diabetes and hypertension moved substantially. Treatment queries and both pulmonary arterial hypertension queries were unchanged across every pair in the sample.",
    "Source categories are a judgment call. The full mapping is in config/source_classes.json and open to disagreement.",
)


def fmt_day(dt: datetime) -> str:
    return f"{dt.day} {dt.strftime('%B %Y')}"


def intro_scope_sentence(metrics: dict[str, Any]) -> str:
    times, runs = collect_times_and_runs(metrics)
    n_runs = len(runs)
    n_citations = int(metrics.get("n_citations") or 0)
    parsed = [parse_z(t) for t in times]
    tmin = min(parsed) if parsed else None
    tmax = max(parsed) if parsed else None
    hours = 0.0
    if tmin and tmax:
        hours = (tmax - tmin).total_seconds() / 3600.0
        if tmin.date() == tmax.date():
            when = f"on {fmt_day(tmin)}"
        else:
            when = f"from {fmt_day(tmin)} to {fmt_day(tmax)}"
    else:
        when = "on a date not available in metrics.json"
    run_word = "run" if n_runs == 1 else "runs"
    return (
        "The scope is small and worth stating up front: 12 queries, 3 conditions, "
        f"{n_runs} {run_word} over {hours:.1f} hours {when}, one locale (Austin, TX), "
        f"Google only, {n_citations} citations in total. That is enough to describe "
        "what was cited. It is not yet enough to say much about change over time — "
        "the collector runs daily, and a longer window will follow."
    )


def section_intro(metrics: dict[str, Any]) -> str:
    paras = [INTRO_LEAD, intro_scope_sentence(metrics), *INTRO_TAIL]
    body = "\n".join(f"<p>{esc(p)}</p>" for p in paras)
    return (
        "<div class='intro'>\n"
        f"{body}\n"
        "</div>"
    )


def section_method(
    metrics: dict[str, Any],
    queries: list[dict[str, Any]],
    cron: str | None,
) -> str:
    times, runs = collect_times_and_runs(metrics)
    parsed = [parse_z(t) for t in times]
    tmin = min(parsed) if parsed else None
    tmax = max(parsed) if parsed else None
    hours = None
    if tmin and tmax:
        hours = (tmax - tmin).total_seconds() / 3600.0
    n_q = metrics.get("aio_presence", {}).get("n_queries")
    conditions = unique_counts(queries, "condition")
    stages = unique_counts(queries, "journey_stage")
    audiences = unique_counts(queries, "audience")
    q_rows = [
        [
            str(q["id"]),
            str(q.get("text") or ""),
            str(q.get("condition") or ""),
            str(q.get("journey_stage") or ""),
            str(q.get("audience") or ""),
        ]
        for q in queries
    ]
    cron_text = cron if cron is not None else "(not found in workflow file)"
    window = "not available in metrics.json"
    if tmin and tmax:
        window = (
            f"{tmin.strftime('%Y-%m-%dT%H:%M:%SZ')} to "
            f"{tmax.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        if hours is not None:
            window += f" ({hours:.1f} hours)"
    parts = [
        "<h2>1. Method</h2>",
        "<dl class='meta'>",
        "<dt>Query set</dt>",
        f"<dd>Configuration, <code>config/queries.json</code>. "
        f"n_queries in metrics.json = {esc(n_q)}. "
        f"File contains n={len(queries)} queries, "
        f"n={len(conditions)} conditions, "
        f"n={len(stages)} journey stages, "
        f"n={len(audiences)} audiences.</dd>",
        "<dt>Locale</dt>",
        f"<dd>Configuration, collector constants in "
        f"<code>citedrift/collect/serpapi.py</code>: "
        f"location=<code>{esc(LOCATION)}</code>, "
        f"hl=<code>{esc(HL)}</code>, gl=<code>{esc(GL)}</code>.</dd>",
        "<dt>Cadence</dt>",
        f"<dd>Configuration, <code>.github/workflows/collect.yml</code>: "
        f"cron <code>{esc(cron_text)}</code> UTC.</dd>",
        "<dt>Run count</dt>",
        f"<dd>Measurement, unique <code>run_id</code> values in metrics.json: "
        f"n={len(runs)}.</dd>",
        "<dt>Date range</dt>",
        f"<dd>Measurement, min/max <code>fetched_at</code> in metrics.json: "
        f"{esc(window)}.</dd>",
        "<dt>Window length</dt>",
        "<dd>The current window is hours, not weeks.</dd>",
        "<dt>Other n</dt>",
        f"<dd>n_manifest_rows={esc(metrics.get('n_manifest_rows'))}, "
        f"n_answers={esc(metrics.get('n_answers'))}, "
        f"n_citations={esc(metrics.get('n_citations'))}.</dd>",
        "</dl>",
        table(
            [
                ("id", False),
                ("text", False),
                ("condition", False),
                ("journey_stage", False),
                ("audience", False),
            ],
            q_rows,
            f"Query set. n={len(queries)}",
        ),
        table(
            [("condition", False), ("n_queries", True)],
            [[name, str(n)] for name, n in conditions],
            f"Queries per condition (configuration). n={len(queries)}",
        ),
        table(
            [("journey_stage", False), ("n_queries", True)],
            [[name, str(n)] for name, n in stages],
            f"Queries per journey stage (configuration). n={len(queries)}",
        ),
        table(
            [("audience", False), ("n_queries", True)],
            [[name, str(n)] for name, n in audiences],
            f"Queries per audience (configuration). n={len(queries)}",
        ),
    ]
    return "\n".join(parts)


def section_presence(metrics: dict[str, Any], query_ids: list[str]) -> str:
    by_q = metrics["aio_presence"]["by_query"]
    rows = []
    chart_rows = []
    attempted_sum = 0
    genuine_absence = 0
    for qid in query_ids:
        row = by_q[qid]
        attempted_sum += int(row["runs_attempted"])
        genuine_absence += int(row["runs_genuine_absence"])
        rows.append(
            [
                qid,
                str(row["runs_attempted"]),
                str(row["runs_with_complete_aio"]),
                str(row["runs_genuine_absence"]),
                str(row["runs_failed_fetch"]),
                fmt_num(row["presence_rate"]),
                str(row["n"]),
            ]
        )
        chart_rows.append(
            (
                qid,
                [(name, int(row[key])) for name, key in PRESENCE_SEGS],
            )
        )
    y_max = max(int(by_q[qid]["runs_attempted"]) for qid in query_ids)
    return "\n".join(
        [
            "<h2>2. AI Overview presence</h2>",
            stacked_counts(
                chart_rows,
                title="Complete fetch by query",
                n=attempted_sum,
                y_max=y_max,
            ),
            table(
                [
                    ("query_id", False),
                    ("runs_attempted", True),
                    ("runs_with_complete_aio", True),
                    ("runs_genuine_absence", True),
                    ("runs_failed_fetch", True),
                    ("complete_fetch_rate", True),
                    ("n", True),
                ],
                rows,
                f"Complete fetch per query. n_queries={metrics['aio_presence']['n_queries']}, "
                f"n_manifest_rows={metrics.get('n_manifest_rows')}",
            ),
            f"<p class='note'>runs_genuine_absence summed across queries: "
            f"{genuine_absence} (n_queries={metrics['aio_presence']['n_queries']}).</p>",
        ]
    )


def class_counts(item: dict[str, Any]) -> dict[str, int]:
    return {cls: int(v["count"]) for cls, v in item.get("classes", {}).items()}


def composition_rows(groups: dict[str, Any], order: tuple[str, ...]) -> list[tuple[str, int, dict[str, int]]]:
    rank = {name: i for i, name in enumerate(order)}
    names = sorted(groups, key=lambda n: (rank.get(n, len(rank)), n))
    out = []
    for name in names:
        item = groups[name]
        out.append((name, int(item["n"]), class_counts(item)))
    return out


def composition_table(
    groups: dict[str, Any],
    order: tuple[str, ...],
    group_header: str,
    caption: str,
) -> str:
    classes: set[str] = set()
    for item in groups.values():
        classes.update(item.get("classes", {}))
    class_list = sorted(classes)
    headers = [(group_header, False), ("n", True)] + [(c, True) for c in class_list]
    rank = {name: i for i, name in enumerate(order)}
    names = sorted(groups, key=lambda n: (rank.get(n, len(rank)), n))
    rows = []
    for name in names:
        item = groups[name]
        row = [name, str(item["n"])]
        for cls in class_list:
            cell = item.get("classes", {}).get(cls)
            if cell is None:
                row.append("0")
            else:
                row.append(f"{cell['count']} ({fmt_pct(cell['pct'])}%)")
        rows.append(row)
    return table(headers, rows, caption)


def patient_journey_groups(block: dict[str, Any]) -> dict[str, Any]:
    """Patient-only journey_stage from existing JSON.

    HCP queries are journey_stage=treatment, so HCP citations (by_audience)
    are subtracted from the treatment row. Other stages are copied.
    """
    stages = block["by_journey_stage"]
    hcp = block.get("by_audience", {}).get("hcp") or {"n": 0, "classes": {}}
    hcp_n = int(hcp.get("n") or 0)
    hcp_counts = class_counts(hcp)
    out: dict[str, Any] = {}
    for name, item in stages.items():
        if name != "treatment":
            out[name] = item
            continue
        counts = class_counts(item)
        for cls, c in hcp_counts.items():
            counts[cls] = counts.get(cls, 0) - c
        n = int(item["n"]) - hcp_n
        classes = {}
        for cls, c in counts.items():
            if c < 0:
                raise ValueError(f"patient treatment {cls} count went negative")
            if c == 0:
                continue
            classes[cls] = {"count": c, "pct": (100.0 * c / n) if n else None}
        out[name] = {"n": n, "classes": classes}
    return out


def class_totals(block: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for item in block["by_journey_stage"].values():
        for cls, c in class_counts(item).items():
            totals[cls] = totals.get(cls, 0) + c
    return totals


def concentration_table(all_pos: dict[str, Any], top: dict[str, Any]) -> str:
    all_counts = class_totals(all_pos)
    top_counts = class_totals(top)
    n_all = int(all_pos["n"])
    n_top = int(top["n"])
    rows = []
    for cls in all_counts:
        c_all = all_counts[cls]
        c_top = top_counts.get(cls, 0)
        ratio = (c_top / c_all) if c_all else None
        rows.append((cls, c_top, c_all, ratio))
    rows.sort(key=lambda r: (-(r[3] if r[3] is not None else -1), r[0]))
    table_rows = [
        [cls, str(c_top), str(c_all), fmt_num(ratio, digits=3)]
        for cls, c_top, c_all, ratio in rows
    ]
    return table(
        [
            ("source_class", False),
            ("n positions 0-2", True),
            ("n all positions", True),
            ("ratio 0-2 / all", True),
        ],
        table_rows,
        f"Position concentration by source_class. n positions 0-2={n_top}, n all positions={n_all}",
    )


def section_composition(metrics: dict[str, Any]) -> str:
    ac = metrics["authority_composition"]
    all_pos = ac["all_positions"]
    top = ac["positions_0_2"]
    patient_all = patient_journey_groups(all_pos)
    patient_top = patient_journey_groups(top)
    n_patient_all = sum(int(v["n"]) for v in patient_all.values())
    n_patient_top = sum(int(v["n"]) for v in patient_top.values())
    return "\n".join(
        [
            "<h2>3. Authority composition by journey stage</h2>",
            stacked_percent(
                composition_rows(all_pos["by_journey_stage"], STAGE_ORDER),
                title="source_class, all positions, all queries",
                n=int(all_pos["n"]),
            ),
            composition_table(
                all_pos["by_journey_stage"],
                STAGE_ORDER,
                "journey_stage",
                f"All queries (patient + HCP). Treatment row mixes audiences. "
                f"n={all_pos['n']}",
            ),
            composition_table(
                patient_all,
                STAGE_ORDER,
                "journey_stage",
                f"Patient-only. Treatment = all-queries treatment minus by_audience HCP. "
                f"n={n_patient_all}",
            ),
            stacked_percent(
                composition_rows(top["by_journey_stage"], STAGE_ORDER),
                title="source_class, positions 0–2, all queries",
                n=int(top["n"]),
            ),
            composition_table(
                top["by_journey_stage"],
                STAGE_ORDER,
                "journey_stage",
                f"All queries (patient + HCP), positions 0–2. Treatment row mixes audiences. "
                f"n={top['n']}",
            ),
            composition_table(
                patient_top,
                STAGE_ORDER,
                "journey_stage",
                f"Patient-only, positions 0–2. Treatment = all-queries treatment minus "
                f"by_audience HCP. n={n_patient_top}",
            ),
            concentration_table(all_pos, top),
        ]
    )


def section_audience(metrics: dict[str, Any]) -> str:
    by_aud = metrics["delivery_mode"]["by_audience"]
    groups = []
    n_aud = 0
    table_rows = []
    for aud in AUDIENCE_ORDER:
        if aud not in by_aud:
            continue
        row = by_aud[aud]
        n_aud += int(row["n"])
        groups.append(
            (
                aud,
                {
                    "inline": int(row["inline"]),
                    "expanded": int(row["expanded"]),
                    "none": int(row["none"]),
                },
            )
        )
        table_rows.append(
            [
                aud,
                str(row["inline"]),
                str(row["expanded"]),
                str(row["none"]),
                str(row["n"]),
            ]
        )
    for aud, row in by_aud.items():
        if aud in AUDIENCE_ORDER:
            continue
        n_aud += int(row["n"])
        groups.append(
            (
                aud,
                {
                    "inline": int(row["inline"]),
                    "expanded": int(row["expanded"]),
                    "none": int(row["none"]),
                },
            )
        )
        table_rows.append(
            [
                aud,
                str(row["inline"]),
                str(row["expanded"]),
                str(row["none"]),
                str(row["n"]),
            ]
        )
    ac = metrics["authority_composition"]
    all_pos = ac["all_positions"]
    top = ac["positions_0_2"]
    return "\n".join(
        [
            "<h2>4. Patient vs HCP</h2>",
            grouped_counts(
                groups,
                ["inline", "expanded", "none"],
                title="Delivery mode by audience",
                n=n_aud,
            ),
            table(
                [
                    ("audience", False),
                    ("inline", True),
                    ("expanded", True),
                    ("none", True),
                    ("n", True),
                ],
                table_rows,
                f"Delivery mode by audience. n={n_aud}",
            ),
            stacked_percent(
                composition_rows(all_pos["by_audience"], AUDIENCE_ORDER),
                title="source_class by audience, all positions",
                n=int(all_pos["n"]),
            ),
            composition_table(
                all_pos["by_audience"],
                AUDIENCE_ORDER,
                "audience",
                f"source_class by audience, all positions. n={all_pos['n']}",
            ),
            stacked_percent(
                composition_rows(top["by_audience"], AUDIENCE_ORDER),
                title="source_class by audience, positions 0–2",
                n=int(top["n"]),
            ),
            composition_table(
                top["by_audience"],
                AUDIENCE_ORDER,
                "audience",
                f"source_class by audience, positions 0–2. n={top['n']}",
            ),
        ]
    )


def zip_identity_pairs(
    metrics: dict[str, Any],
    kind: str,
    query_ids: list[str],
) -> list[dict[str, Any]]:
    url_block = metrics[kind]["url_canonical"]
    dom_block = metrics[kind]["domain"]
    out = []
    for qid in query_ids:
        url_pairs = url_block["by_query"].get(qid, {}).get("pairs", [])
        dom_pairs = {
            (p["run_id_a"], p["run_id_b"]): p
            for p in dom_block["by_query"].get(qid, {}).get("pairs", [])
        }
        for up in url_pairs:
            dp = dom_pairs.get((up["run_id_a"], up["run_id_b"]), {})
            out.append({"query_id": qid, "url": up, "domain": dp})
    return out


def metric_cell(pair: dict[str, Any], field: str) -> str:
    value = pair.get(field)
    note = pair.get(f"{field}_note")
    if value is None and note:
        return f"null ({note})"
    return fmt_num(value)


def interval_minutes(fetched_a: str | None, fetched_b: str | None) -> str:
    if not fetched_a or not fetched_b:
        return "null"
    delta = parse_z(fetched_b) - parse_z(fetched_a)
    return f"{delta.total_seconds() / 60.0:.1f}"


def section_stability(
    metrics: dict[str, Any],
    query_ids: list[str],
    meta: dict[str, dict[str, Any]],
) -> str:
    j_pairs = zip_identity_pairs(metrics, "jaccard", query_ids)
    r_pairs = zip_identity_pairs(metrics, "rbo", query_ids)
    j_n = metrics["jaccard"]["url_canonical"]["n_pairs"]
    j_null = metrics["jaccard"]["url_canonical"]["n_null_excluded"]
    r_null = metrics["rbo"]["url_canonical"]["n_null_excluded"]
    r_by = {(x["query_id"], x["url"]["run_id_a"], x["url"]["run_id_b"]): x for x in r_pairs}
    rows = []
    for item in j_pairs:
        key = (item["query_id"], item["url"]["run_id_a"], item["url"]["run_id_b"])
        rp = r_by.get(key, {"url": {}, "domain": {}})
        qid = item["query_id"]
        rows.append(
            [
                qid,
                str(item["url"]["run_id_a"]),
                str(item["url"]["run_id_b"]),
                str(meta.get(qid, {}).get("audience") or "unknown"),
                interval_minutes(item["url"].get("fetched_at_a"), item["url"].get("fetched_at_b")),
                metric_cell(item["url"], "jaccard"),
                metric_cell(item["domain"], "jaccard"),
                metric_cell(rp["url"], "rbo"),
                metric_cell(rp["domain"], "rbo"),
            ]
        )
    return "\n".join(
        [
            "<h2>5. Citation stability</h2>",
            table(
                [
                    ("query_id", False),
                    ("run_a", False),
                    ("run_b", False),
                    ("audience", False),
                    ("interval_minutes", True),
                    ("jaccard url_canonical", True),
                    ("jaccard domain", True),
                    ("rbo url_canonical", True),
                    ("rbo domain", True),
                ],
                rows,
                f"Consecutive complete-run pairs. n_pairs={j_n}, "
                f"n_null_excluded Jaccard={j_null} RBO={r_null}",
            ),
        ]
    )


def section_manufacturer(metrics: dict[str, Any]) -> str:
    block = metrics["manufacturer_presence"]
    rows = []
    run_rows = []
    n_q = 0
    for qid, item in block.items():
        n_q += 1
        rows.append(
            [
                qid,
                fmt_num(item["any_manufacturer"]),
                str(item["n_manufacturer"]),
                str(item["n_citations"]),
                str(item["n"]),
            ]
        )
        for run in item.get("by_run", []):
            run_rows.append(
                [
                    qid,
                    str(run["run_id"]),
                    str(run.get("fetched_at") or ""),
                    fmt_num(run["any_manufacturer"]),
                    str(run["n_manufacturer"]),
                    str(run["n_citations"]),
                    str(run["n"]),
                ]
            )
    return "\n".join(
        [
            "<h2>6. Manufacturer presence on branded queries</h2>",
            "<p>Jardiance's manufacturer domain appeared in four runs and disappeared in the fifth, while Opsumit's held at 3 in all five. A brand's presence in its own branded AI Overview isn't stable.</p>",
            table(
                [
                    ("query_id", False),
                    ("any_manufacturer", False),
                    ("n_manufacturer", True),
                    ("n_citations", True),
                    ("n", True),
                ],
                rows,
                f"Manufacturer citations, branded queries. n_queries={n_q}",
            ),
            table(
                [
                    ("query_id", False),
                    ("run_id", False),
                    ("fetched_at", False),
                    ("any_manufacturer", False),
                    ("n_manufacturer", True),
                    ("n_citations", True),
                    ("n", True),
                ],
                run_rows,
                f"Manufacturer citations by run. n_rows={len(run_rows)}",
            ),
        ]
    )


def _calendar_dates_phrase(n_dates: int) -> str:
    if n_dates == 1:
        return "One calendar date"
    if n_dates == 2:
        return "Two calendar dates"
    return f"{n_dates} calendar dates"


def limitation_window_line(metrics: dict[str, Any]) -> str:
    times, runs = collect_times_and_runs(metrics)
    parsed = [parse_z(t) for t in times]
    n_runs = len(runs)
    n_dates = len({dt.date() for dt in parsed})
    hours = 0.0
    if parsed:
        hours = (max(parsed) - min(parsed)).total_seconds() / 3600.0
    run_word = "run" if n_runs == 1 else "runs"
    return f"{_calendar_dates_phrase(n_dates)}, {hours:.1f} hours, {n_runs} {run_word}"


def clinician_limitation_line(
    metrics: dict[str, Any],
    queries: list[dict[str, Any]],
) -> str:
    n_q = sum(1 for q in queries if str(q.get("audience") or "") == "hcp")
    n_complete = int(
        metrics.get("delivery_mode", {}).get("by_audience", {}).get("hcp", {}).get("n") or 0
    )
    n_top = int(
        metrics.get("authority_composition", {})
        .get("positions_0_2", {})
        .get("by_audience", {})
        .get("hcp", {})
        .get("n")
        or 0
    )
    return (
        f"Clinician-phrased findings rest on {n_q} queries, "
        f"{n_complete} complete observations, {n_top} top-three citations"
    )


def section_limitations(
    metrics: dict[str, Any],
    queries: list[dict[str, Any]],
    cron: str | None,
    n_runs: int,
) -> str:
    cron_text = cron if cron is not None else "(not found in workflow file)"
    return "\n".join(
        [
            "<h2>7. Limitations</h2>",
            "<ul>",
            f"<li>Run count: n={n_runs} (unique run_id in metrics.json).</li>",
            f"<li>Single locale (configuration): location=<code>{esc(LOCATION)}</code>, "
            f"hl=<code>{esc(HL)}</code>, gl=<code>{esc(GL)}</code>.</li>",
            "<li>Single engine (configuration): Google, via the collector adapter.</li>",
            f"<li>{esc(limitation_window_line(metrics))}.</li>",
            f"<li>{esc(clinician_limitation_line(metrics, queries))}.</li>",
            f"<li>Cadence (configuration): cron <code>{esc(cron_text)}</code> UTC.</li>",
            "</ul>",
        ]
    )


def render_html(
    metrics: dict[str, Any],
    queries: list[dict[str, Any]],
    cron: str | None,
) -> str:
    meta = query_meta(queries)
    query_ids = [str(q["id"]) for q in queries]
    extra = [
        qid
        for qid in metrics.get("aio_presence", {}).get("by_query", {})
        if qid not in meta
    ]
    query_ids = query_ids + extra
    times, runs = collect_times_and_runs(metrics)
    body = "\n".join(
        [
            "<h1>CiteDrift</h1>",
            section_intro(metrics),
            "<p class='note'>Numbers in the tables and charts are from data/analysis/metrics.json. "
            "Locale and cadence are configuration, not measurements.</p>",
            section_method(metrics, queries, cron),
            section_presence(metrics, query_ids),
            section_composition(metrics),
            section_audience(metrics),
            section_stability(metrics, query_ids, meta),
            section_manufacturer(metrics),
            section_limitations(metrics, queries, cron, len(runs)),
        ]
    )
    return (
        "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
        "<meta charset='utf-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>\n"
        "<title>CiteDrift</title>\n"
        f"<style>\n{css()}\n</style>\n"
        "</head>\n<body>\n<main>\n"
        f"{body}\n"
        "</main>\n</body>\n</html>\n"
    )


def report_all(
    metrics_path: Path = METRICS_PATH,
    queries_path: Path = QUERIES_PATH,
    workflow_path: Path = WORKFLOW_PATH,
    out_path: Path = OUT_PATH,
) -> Path:
    if not metrics_path.is_file():
        raise FileNotFoundError(metrics_path)
    if not queries_path.is_file():
        raise FileNotFoundError(queries_path)
    metrics = load_json(metrics_path)
    queries = load_json(queries_path)
    if not isinstance(queries, list):
        raise ValueError("config/queries.json must be a JSON array")
    cron = cadence_cron(workflow_path)
    html = render_html(metrics, queries, cron)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main() -> int:
    try:
        path = report_all()
    except FileNotFoundError as exc:
        print(f"missing {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

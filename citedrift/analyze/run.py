"""Compute drift metrics. Derived; rebuilt each run. No network."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from citedrift.analyze.jaccard import jaccard
from citedrift.analyze.rbo import P as RBO_P
from citedrift.analyze.rbo import rbo
from citedrift.analyze.survival import survival_curve
from citedrift.parse.run import resolve_aio_complete

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw"
PARSED_ROOT = ROOT / "data" / "parsed"
QUERIES_PATH = ROOT / "config" / "queries.json"
OUT_PATH = ROOT / "data" / "analysis" / "metrics.json"

ID_KEYS = ("url_canonical", "domain")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def load_queries(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("config/queries.json must be a JSON array")
    return data


def query_meta(queries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(q["id"]): q for q in queries}


def classify_manifest_row(row: dict[str, Any]) -> str:
    complete, _ = resolve_aio_complete(row)
    if complete:
        return "complete"
    error = row.get("error")
    if error:
        return "failed_fetch"
    return "genuine_absence"


def load_manifests(raw_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not raw_root.is_dir():
        return rows
    for run_dir in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        manifest = run_dir / "manifest.jsonl"
        if not manifest.is_file():
            continue
        for row in load_jsonl(manifest):
            item = dict(row)
            item["run_id"] = run_dir.name
            rows.append(item)
    return rows


def ranked_ids(cites: list[dict[str, Any]], key: str) -> list[str]:
    ordered = sorted(cites, key=lambda r: int(r.get("position") if r.get("position") is not None else 10**9))
    out: list[str] = []
    seen: set[str] = set()
    for row in ordered:
        val = str(row.get(key) or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def empty_presence() -> dict[str, Any]:
    return {
        "runs_attempted": 0,
        "runs_with_complete_aio": 0,
        "runs_failed_fetch": 0,
        "runs_genuine_absence": 0,
        "presence_rate": None,
        "n": 0,
    }


def presence_from_manifests(
    manifests: list[dict[str, Any]],
    query_ids: list[str],
) -> dict[str, Any]:
    by_query: dict[str, dict[str, Any]] = {qid: empty_presence() for qid in query_ids}
    for row in manifests:
        qid = str(row.get("query_id") or "")
        if not qid:
            continue
        bucket = by_query.setdefault(qid, empty_presence())
        bucket["runs_attempted"] += 1
        kind = classify_manifest_row(row)
        if kind == "complete":
            bucket["runs_with_complete_aio"] += 1
        elif kind == "failed_fetch":
            bucket["runs_failed_fetch"] += 1
        else:
            bucket["runs_genuine_absence"] += 1
    for bucket in by_query.values():
        n = bucket["runs_attempted"]
        bucket["n"] = n
        complete = bucket["runs_with_complete_aio"]
        bucket["presence_rate"] = (complete / n) if n else None
    return {"by_query": by_query, "n_queries": len(by_query)}


def delivery_from_manifests(
    manifests: list[dict[str, Any]],
    meta: dict[str, dict[str, Any]],
    query_ids: list[str],
) -> dict[str, Any]:
    def zero() -> dict[str, int]:
        return {"inline": 0, "expanded": 0, "none": 0, "n": 0}

    by_query: dict[str, dict[str, int]] = {qid: zero() for qid in query_ids}
    by_audience: dict[str, dict[str, int]] = {}
    for row in manifests:
        qid = str(row.get("query_id") or "")
        if not qid:
            continue
        mode = str(row.get("delivery_mode") or "none")
        if mode not in {"inline", "expanded", "none"}:
            mode = "none"
        bucket = by_query.setdefault(qid, zero())
        bucket[mode] += 1
        bucket["n"] += 1
        if classify_manifest_row(row) != "complete":
            continue
        audience = str(meta.get(qid, {}).get("audience") or "unknown")
        aud = by_audience.setdefault(audience, zero())
        aud[mode] += 1
        aud["n"] += 1
    return {"by_query": by_query, "by_audience": by_audience}


def complete_runs_by_query(manifests: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in manifests:
        if classify_manifest_row(row) != "complete":
            continue
        grouped[str(row["query_id"])].append(row)
    for qid, rows in grouped.items():
        rows.sort(key=lambda r: (str(r.get("fetched_at") or ""), str(r.get("run_id") or "")))
        grouped[qid] = rows
    return dict(grouped)


def group_citations(
    citations: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in citations:
        qid = str(row.get("query_id") or "")
        run_id = str(row.get("run_id") or "")
        if not qid or not run_id:
            continue
        grouped[(qid, run_id)].append(row)
    return dict(grouped)


def _consecutive_pairs(
    complete: dict[str, list[dict[str, Any]]],
    cites: dict[tuple[str, str], list[dict[str, Any]]],
    query_ids: list[str],
    kind: str,
) -> dict[str, Any]:
    score = jaccard if kind == "jaccard" else rbo
    value_key = "jaccard" if kind == "jaccard" else "rbo"
    note_key = f"{value_key}_note"
    per_id: dict[str, Any] = {}
    for id_key in ID_KEYS:
        values: list[float] = []
        excluded = 0
        pair_count = 0
        q_block: dict[str, Any] = {}
        for qid in query_ids:
            runs = complete.get(qid, [])
            q_values: list[float] = []
            q_excl = 0
            q_pairs: list[dict[str, Any]] = []
            for i in range(len(runs) - 1):
                a, b = runs[i], runs[i + 1]
                cites_a = cites.get((qid, str(a["run_id"])), [])
                cites_b = cites.get((qid, str(b["run_id"])), [])
                if kind == "jaccard":
                    value, note = score(
                        set(ranked_ids(cites_a, id_key)),
                        set(ranked_ids(cites_b, id_key)),
                    )
                else:
                    value, note = score(
                        ranked_ids(cites_a, id_key),
                        ranked_ids(cites_b, id_key),
                    )
                item: dict[str, Any] = {
                    "run_id_a": a["run_id"],
                    "run_id_b": b["run_id"],
                    "fetched_at_a": a.get("fetched_at"),
                    "fetched_at_b": b.get("fetched_at"),
                    value_key: value,
                    note_key: note,
                    "n": 2,
                }
                if kind == "rbo":
                    item["p"] = RBO_P
                q_pairs.append(item)
                pair_count += 1
                if value is None:
                    excluded += 1
                    q_excl += 1
                else:
                    values.append(value)
                    q_values.append(value)
            q_block[qid] = {
                "pairs": q_pairs,
                "n_pairs": len(q_pairs),
                "n_null_excluded": q_excl,
                "values": q_values,
            }
        block: dict[str, Any] = {
            "by_query": q_block,
            "n_pairs": pair_count,
            "n_null_excluded": excluded,
            "values": values,
        }
        if kind == "rbo":
            block["p"] = RBO_P
        per_id[id_key] = block
    return per_id


def survival_metrics(
    complete: dict[str, list[dict[str, Any]]],
    cites: dict[tuple[str, str], list[dict[str, Any]]],
    query_ids: list[str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for id_key in ID_KEYS:
        by_query: dict[str, Any] = {}
        max_k = 0
        for qid in query_ids:
            runs = complete.get(qid, [])
            sets = [set(ranked_ids(cites.get((qid, str(r["run_id"])), []), id_key)) for r in runs]
            curve = survival_curve(sets)
            serialized = {str(k): v for k, v in curve.items()}
            by_query[qid] = {
                "by_k": serialized,
                "n_complete_runs": len(runs),
                "k_max": (len(runs) - 1) if runs else 0,
            }
            if curve:
                max_k = max(max_k, max(curve))
        overall: dict[str, Any] = {}
        for k in range(1, max_k + 1):
            survived = 0
            instances = 0
            pairs = 0
            for qid in query_ids:
                runs = complete.get(qid, [])
                sets = [set(ranked_ids(cites.get((qid, str(r["run_id"])), []), id_key)) for r in runs]
                n_runs = len(sets)
                for i in range(n_runs - k):
                    start = sets[i]
                    later = sets[i + k]
                    if not start:
                        continue
                    pairs += 1
                    for src in start:
                        instances += 1
                        if src in later:
                            survived += 1
            overall[str(k)] = {
                "rate": (survived / instances) if instances else None,
                "n_instances": instances,
                "n_pairs": pairs,
                "n_survived": survived,
            }
        out[id_key] = {"by_query": by_query, "overall": overall, "k_max": max_k}
    return out


def class_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row.get("source_class") or "unclassified")
        counts[name] = counts.get(name, 0) + 1
    n = len(rows)
    classes = {
        name: {"count": c, "pct": (100.0 * c / n) if n else None}
        for name, c in sorted(counts.items())
    }
    return {"n": n, "classes": classes}


def slice_by(citations: list[dict[str, Any]], meta: dict[str, dict[str, Any]], field: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in citations:
        qid = str(row.get("query_id") or "")
        key = str(meta.get(qid, {}).get(field) or "unknown")
        buckets[key].append(row)
    return {name: class_distribution(rows) for name, rows in sorted(buckets.items())}


def authority_composition(
    citations: list[dict[str, Any]],
    meta: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    top = []
    for row in citations:
        pos = row.get("position")
        if pos is None:
            continue
        if int(pos) <= 2:
            top.append(row)

    def block(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "by_journey_stage": slice_by(rows, meta, "journey_stage"),
            "by_audience": slice_by(rows, meta, "audience"),
            "by_condition": slice_by(rows, meta, "condition"),
            "n": len(rows),
        }

    return {"all_positions": block(citations), "positions_0_2": block(top)}


def manufacturer_presence(
    citations: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    complete: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    branded = [q for q in queries if q.get("journey_stage") == "branded"]
    cites_by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    all_by_q: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in citations:
        qid = str(row.get("query_id") or "")
        run_id = str(row.get("run_id") or "")
        all_by_q[qid].append(row)
        cites_by[(qid, run_id)].append(row)
    out: dict[str, Any] = {}
    for q in branded:
        qid = str(q["id"])
        rows = all_by_q.get(qid, [])
        n_man = sum(1 for r in rows if r.get("source_class") == "manufacturer")
        by_run = []
        for run in complete.get(qid, []):
            run_id = str(run["run_id"])
            run_rows = cites_by.get((qid, run_id), [])
            n_run_man = sum(1 for r in run_rows if r.get("source_class") == "manufacturer")
            by_run.append(
                {
                    "run_id": run_id,
                    "fetched_at": run.get("fetched_at"),
                    "n_citations": len(run_rows),
                    "n_manufacturer": n_run_man,
                    "any_manufacturer": n_run_man > 0,
                    "n": len(run_rows),
                }
            )
        out[qid] = {
            "n_citations": len(rows),
            "n_manufacturer": n_man,
            "any_manufacturer": n_man > 0,
            "n": len(rows),
            "by_run": by_run,
        }
    return out


def build_metrics(
    manifests: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    n_answers: int = 0,
) -> dict[str, Any]:
    meta = query_meta(queries)
    query_ids = [str(q["id"]) for q in queries]
    extra = []
    seen = set(query_ids)
    for row in manifests:
        qid = str(row.get("query_id") or "")
        if qid and qid not in seen:
            extra.append(qid)
            seen.add(qid)
    query_ids = query_ids + extra
    complete = complete_runs_by_query(manifests)
    cites = group_citations(citations)
    jaccard_block = _consecutive_pairs(complete, cites, query_ids, "jaccard")
    rbo_block = _consecutive_pairs(complete, cites, query_ids, "rbo")
    return {
        "n_manifest_rows": len(manifests),
        "n_citations": len(citations),
        "n_answers": n_answers,
        "aio_presence": presence_from_manifests(manifests, query_ids),
        "delivery_mode": delivery_from_manifests(manifests, meta, query_ids),
        "jaccard": jaccard_block,
        "rbo": rbo_block,
        "source_survival": survival_metrics(complete, cites, query_ids),
        "authority_composition": authority_composition(citations, meta),
        "manufacturer_presence": manufacturer_presence(citations, queries, complete),
    }


def fmt_num(value: float | int | None, digits: int = 4) -> str:
    if value is None:
        return "null"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return f"{value:.{digits}f}"


def print_summary(metrics: dict[str, Any]) -> None:
    print("AIO presence")
    print(
        f"{'query_id':<16}  {'attempted':>9}  {'complete':>8}  "
        f"{'failed_fetch':>12}  {'genuine_absence':>15}  {'rate':>6}"
    )
    for qid, row in metrics["aio_presence"]["by_query"].items():
        print(
            f"{qid:<16}  {row['runs_attempted']:>9}  {row['runs_with_complete_aio']:>8}  "
            f"{row['runs_failed_fetch']:>12}  {row['runs_genuine_absence']:>15}  "
            f"{fmt_num(row['presence_rate']):>6}"
        )
    print()
    print("Delivery mode (all attempts / audience among complete)")
    print(f"{'query_id':<16}  {'inline':>6}  {'expanded':>8}  {'none':>4}  {'n':>4}")
    for qid, row in metrics["delivery_mode"]["by_query"].items():
        print(
            f"{qid:<16}  {row['inline']:>6}  {row['expanded']:>8}  {row['none']:>4}  {row['n']:>4}"
        )
    print(f"{'audience':<16}  {'inline':>6}  {'expanded':>8}  {'none':>4}  {'n':>4}")
    for aud, row in metrics["delivery_mode"]["by_audience"].items():
        print(
            f"{aud:<16}  {row['inline']:>6}  {row['expanded']:>8}  {row['none']:>4}  {row['n']:>4}"
        )
    print()
    for label, key in (("Jaccard", "jaccard"), ("RBO", "rbo")):
        for id_key, block in metrics[key].items():
            val_name = "jaccard" if key == "jaccard" else "rbo"
            note_name = f"{val_name}_note"
            print(
                f"{label} {id_key}  n_pairs={block['n_pairs']}  "
                f"n_null_excluded={block['n_null_excluded']}"
            )
            print(f"{'query_id':<16}  {'run_a':<18}  {'run_b':<18}  {val_name:>8}  note")
            for qid, qblock in block["by_query"].items():
                for pair in qblock["pairs"]:
                    print(
                        f"{qid:<16}  {str(pair['run_id_a']):<18}  {str(pair['run_id_b']):<18}  "
                        f"{fmt_num(pair[val_name]):>8}  {pair[note_name] or ''}"
                    )
            print()
    print("Source survival (overall)")
    for id_key, block in metrics["source_survival"].items():
        print(f"{id_key}  k_max={block['k_max']}")
        print(f"{'k':>4}  {'rate':>8}  {'n_instances':>12}  {'n_pairs':>7}")
        for k, row in block["overall"].items():
            print(
                f"{k:>4}  {fmt_num(row['rate']):>8}  {row['n_instances']:>12}  {row['n_pairs']:>7}"
            )
        print()
    print("Authority composition n (all / positions 0-2)")
    ac = metrics["authority_composition"]
    print(f"all_positions n={ac['all_positions']['n']}")
    print(f"positions_0_2 n={ac['positions_0_2']['n']}")
    print()
    print("Manufacturer presence (branded queries)")
    print(f"{'query_id':<16}  {'any':<5}  {'n_manufacturer':>14}  {'n_citations':>12}")
    for qid, row in metrics["manufacturer_presence"].items():
        print(
            f"{qid:<16}  {str(row['any_manufacturer']):<5}  "
            f"{row['n_manufacturer']:>14}  {row['n_citations']:>12}"
        )


def analyze_all(
    raw_root: Path = RAW_ROOT,
    citations_path: Path = PARSED_ROOT / "citations_normalized.jsonl",
    answers_path: Path = PARSED_ROOT / "answers.jsonl",
    queries_path: Path = QUERIES_PATH,
    out_path: Path = OUT_PATH,
) -> dict[str, Any]:
    # answers.jsonl is successes only; presence uses manifests. Still require it exists
    # so a missing parse is visible rather than silently analyzing citations alone.
    if not answers_path.is_file():
        raise FileNotFoundError(answers_path)
    if not citations_path.is_file():
        raise FileNotFoundError(citations_path)
    if not queries_path.is_file():
        raise FileNotFoundError(queries_path)
    manifests = load_manifests(raw_root)
    citations = load_jsonl(citations_path)
    answers = load_jsonl(answers_path)
    queries = load_queries(queries_path)
    metrics = build_metrics(manifests, citations, queries, n_answers=len(answers))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metrics


def main() -> int:
    try:
        metrics = analyze_all()
    except FileNotFoundError as exc:
        print(f"missing {exc}", file=sys.stderr)
        return 1
    print_summary(metrics)
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

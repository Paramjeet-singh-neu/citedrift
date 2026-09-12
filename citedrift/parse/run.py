"""Walk data/raw and write data/parsed JSONL. Derived; rebuilt each run."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from citedrift.parse.blocks import answer_hash, assemble_answer
from citedrift.parse.refs import keep_references

log = logging.getLogger("citedrift.parse")

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw"
PARSED_ROOT = ROOT / "data" / "parsed"


def resolve_aio_complete(row: dict[str, Any]) -> tuple[bool, str]:
    if "aio_complete" in row:
        return bool(row["aio_complete"]), "field"
    error = row.get("error")
    ref_count = row.get("reference_count") or 0
    derived = error is None and int(ref_count) > 0
    return derived, "derived"


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def aio_payload(run_dir: Path, query_id: str, delivery_mode: str) -> dict[str, Any]:
    name = f"{query_id}_aio.json" if delivery_mode == "expanded" else f"{query_id}_main.json"
    path = run_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


def parse_observation(
    run_id: str,
    row: dict[str, Any],
    payload: dict[str, Any],
    aio_complete_source: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    query_id = str(row["query_id"])
    delivery_mode = str(row.get("delivery_mode") or "none")
    aio = payload.get("ai_overview")
    if not isinstance(aio, dict):
        aio = {}
    text = assemble_answer(aio.get("text_blocks") if isinstance(aio.get("text_blocks"), list) else [])
    answer = {
        "run_id": run_id,
        "query_id": query_id,
        "answer_text": text,
        "answer_hash": answer_hash(text),
        "delivery_mode": delivery_mode,
        "fetched_at": row.get("fetched_at"),
        "runner": row.get("runner"),
        "aio_complete_source": aio_complete_source,
    }
    kept = keep_references(aio.get("references") or [], delivery_mode)
    citations = []
    for position, ref in enumerate(kept):
        citations.append(
            {
                "run_id": run_id,
                "query_id": query_id,
                "position": position,
                "source": ref.get("source"),
                "link": ref.get("link"),
                "title": ref.get("title"),
                "snippet": ref.get("snippet"),
                "delivery_mode": delivery_mode,
                "fetched_at": row.get("fetched_at"),
                "runner": row.get("runner"),
            }
        )
    return answer, citations


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_all(raw_root: Path = RAW_ROOT, parsed_root: Path = PARSED_ROOT) -> dict[str, int]:
    answers: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    runs = 0
    skipped_incomplete = 0
    derived_count = 0

    if not raw_root.is_dir():
        print(f"missing {raw_root}", file=sys.stderr)
        return {
            "runs": 0,
            "observations": 0,
            "citations": 0,
            "skipped_incomplete": 0,
            "derived": 0,
        }

    for run_dir in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        manifest = run_dir / "manifest.jsonl"
        if not manifest.is_file():
            continue
        runs += 1
        run_id = run_dir.name
        for row in load_manifest(manifest):
            complete, source = resolve_aio_complete(row)
            if source == "derived":
                derived_count += 1
            if not complete:
                skipped_incomplete += 1
                continue
            delivery_mode = str(row.get("delivery_mode") or "none")
            payload = aio_payload(run_dir, str(row["query_id"]), delivery_mode)
            answer, cites = parse_observation(run_id, row, payload, source)
            answers.append(answer)
            citations.extend(cites)

    write_jsonl(parsed_root / "answers.jsonl", answers)
    write_jsonl(parsed_root / "citations.jsonl", citations)
    return {
        "runs": runs,
        "observations": len(answers),
        "citations": len(citations),
        "skipped_incomplete": skipped_incomplete,
        "derived": derived_count,
    }


def print_summary(stats: dict[str, int]) -> None:
    print(f"runs processed: {stats['runs']}")
    print(f"observations: {stats['observations']}")
    print(f"citations: {stats['citations']}")
    print(f"skipped aio_complete=false: {stats['skipped_incomplete']}")
    print(f"aio_complete derived (pre-fix rows): {stats['derived']}")


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    stats = parse_all()
    print_summary(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

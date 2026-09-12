"""One collection run: queries.json → data/raw/<run_id>/."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from citedrift.collect.serpapi import SerpApiAdapter

ROOT = Path(__file__).resolve().parents[2]
QUERIES_PATH = ROOT / "config" / "queries.json"
RAW_ROOT = ROOT / "data" / "raw"


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_id_now() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_queries(path: Path = QUERIES_PATH) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("config/queries.json must be a JSON array")
    queries: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            raise SystemExit("each query must have id and text")
        queries.append(item)
    return queries


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_manifest(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def top_level_aio(payload: dict) -> dict | None:
    aio = payload.get("ai_overview")
    if isinstance(aio, dict) and aio:
        return aio
    return None


def reference_list(aio: dict | None) -> list:
    if not aio:
        return []
    refs = aio.get("references")
    return refs if isinstance(refs, list) else []


def collect_one(
    adapter: SerpApiAdapter,
    query: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    query_id = str(query["id"])
    text = str(query["text"])
    used_before = adapter.searches_used
    fetched_at = utc_now()
    error: str | None = None
    delivery_mode = "none"
    aio_present = False
    reference_count = 0

    try:
        main_payload = adapter.google_search(text)
        write_json(run_dir / f"{query_id}_main.json", main_payload)
        if isinstance(main_payload.get("error"), str):
            error = main_payload["error"]
        aio = top_level_aio(main_payload)
        aio_present = aio is not None
        refs = reference_list(aio)

        if aio is not None and aio.get("page_token") and not refs:
            try:
                aio_payload = adapter.google_ai_overview(str(aio["page_token"]))
                write_json(run_dir / f"{query_id}_aio.json", aio_payload)
            except Exception as exc:
                delivery_mode = "none"
                if error is None:
                    error = str(exc)
            else:
                if isinstance(aio_payload.get("error"), str) and error is None:
                    error = aio_payload["error"]
                exp_refs = reference_list(top_level_aio(aio_payload))
                if exp_refs:
                    delivery_mode = "expanded"
                    reference_count = len(exp_refs)
                else:
                    delivery_mode = "none"
                    if error is None:
                        error = "expanded_aio_empty"
        elif aio is not None:
            delivery_mode = "inline"
            reference_count = len(refs)

        if aio_present and reference_count == 0 and error is None:
            error = "aio_without_references"
    except Exception as exc:
        if error is None:
            error = str(exc)

    return {
        "query_id": query_id,
        "fetched_at": iso_z(fetched_at),
        "aio_present": aio_present,
        "delivery_mode": delivery_mode,
        "reference_count": reference_count,
        "searches_used": adapter.searches_used - used_before,
        "error": error,
    }


def print_summary(rows: list[dict[str, Any]], searches_used: int) -> None:
    cols = ("query_id", "aio_present", "delivery_mode", "reference_count")
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols} if rows else {c: len(c) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("  ".join("-" * widths[c] for c in cols))
    for row in rows:
        print("  ".join(str(row[c]).ljust(widths[c]) for c in cols))
    print(f"total searches used: {searches_used}")


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        print("SERPAPI_KEY is not set", file=sys.stderr)
        return 1
    if not QUERIES_PATH.is_file():
        print(f"missing {QUERIES_PATH}", file=sys.stderr)
        return 1

    queries = load_queries()
    run_id = run_id_now()
    run_dir = RAW_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.jsonl"

    adapter = SerpApiAdapter(api_key)
    rows: list[dict[str, Any]] = []
    aborted = False

    for query in queries:
        if adapter.remaining() < 2:
            aborted = True
            print(
                f"abort: remaining searches {adapter.remaining()} < 2",
                file=sys.stderr,
            )
            break
        row = collect_one(adapter, query, run_dir)
        append_manifest(manifest_path, row)
        rows.append(row)

    print_summary(rows, adapter.searches_used)
    if aborted:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

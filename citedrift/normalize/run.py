"""Read citations.jsonl, write citations_normalized.jsonl. Syntactic only."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from citedrift.normalize.classes import load_source_classes, source_class
from citedrift.normalize.url import canonicalize, is_resolvable, registrable_domain, tld_class

ROOT = Path(__file__).resolve().parents[2]
IN_PATH = ROOT / "data" / "parsed" / "citations.jsonl"
OUT_PATH = ROOT / "data" / "parsed" / "citations_normalized.jsonl"


def normalize_row(row: dict[str, Any], class_map: dict[str, str]) -> dict[str, Any]:
    link = str(row.get("link") or "")
    out = dict(row)
    out["url_raw_first_seen"] = link
    out["url_canonical"] = canonicalize(link) if link else ""
    out["url_resolvable"] = is_resolvable(link) if link else False
    out["domain"] = registrable_domain(out["url_canonical"] or link) if link else ""
    out["tld_class"] = tld_class(out["url_canonical"] or link) if link else "other"
    out["source_class"] = source_class(out["domain"], class_map) if out["domain"] else "unclassified"
    return out


def normalize_all(in_path: Path = IN_PATH, out_path: Path = OUT_PATH) -> Counter[str]:
    class_map = load_source_classes()
    unclassified: Counter[str] = Counter()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows_out = 0
    with in_path.open(encoding="utf-8") as fh_in, out_path.open("w", encoding="utf-8") as fh_out:
        for line in fh_in:
            line = line.strip()
            if not line:
                continue
            row = normalize_row(json.loads(line), class_map)
            fh_out.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows_out += 1
            if row["source_class"] == "unclassified" and row["domain"]:
                unclassified[row["domain"]] += 1
    return unclassified


def print_unclassified(counts: Counter[str]) -> None:
    print("unclassified domains:")
    if not counts:
        print("  (none)")
        return
    for domain, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {domain}  {n}")


def main() -> int:
    if not IN_PATH.is_file():
        print(f"missing {IN_PATH}", file=sys.stderr)
        return 1
    counts = normalize_all()
    print_unclassified(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

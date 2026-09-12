"""Throwaway Phase 0 spike. Not the collector."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERPAPI_SEARCH = "https://serpapi.com/search"

QUERIES = [
    "type 2 diabetes treatment options",
    "SGLT2 inhibitor vs GLP-1 first line type 2 diabetes",
]


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


def slugify(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
    return slug[:80] or "query"


def serpapi_get(params: dict[str, str]) -> dict:
    url = SERPAPI_SEARCH + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise SystemExit(f"HTTP {exc.code} from SerpApi: {body[:500]}") from exc
        return payload
    return json.loads(body)


def write_json(name: str, payload: dict) -> Path:
    path = ROOT / name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def print_references(query: str, aio: dict) -> None:
    refs = aio.get("references") or []
    print(f"AIO     {query!r}")
    print(f"        references={len(refs)}")
    if not refs:
        print("        SOURCE LIST MISSING — text without citations is a failed gate")
        return
    for ref in refs:
        position = ref.get("index", "")
        link = ref.get("link", "")
        print(f"        {position}  {link}")


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        raise SystemExit("SERPAPI_KEY is not set")

    for query in QUERIES:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = slugify(query)
        main_name = f"raw_{ts}_{slug}_main.json"

        payload = serpapi_get(
            {
                "engine": "google",
                "q": query,
                "api_key": api_key,
                "location": "Austin, Texas, United States",
                "hl": "en",
                "gl": "us",
                "no_cache": "true",
            }
        )
        write_json(main_name, payload)
        print(f"SAVED   {main_name}")

        # Top-level only. related_questions also contain ai_overview / 
        # serpapi_ai_overview_link — those are PAA, not the main AIO.
        aio = payload.get("ai_overview")
        if not isinstance(aio, dict) or not aio:
            print(f"NO AIO  {query!r}")
            print()
            continue

        if aio.get("page_token") and not aio.get("references"):
            aio_name = f"raw_{ts}_{slug}_aio.json"
            aio_payload = serpapi_get(
                {
                    "engine": "google_ai_overview",
                    "page_token": aio["page_token"],
                    "api_key": api_key,
                    "no_cache": "true",
                }
            )
            write_json(aio_name, aio_payload)
            print(f"SAVED   {aio_name}")
            aio = aio_payload.get("ai_overview")
            if not isinstance(aio, dict) or not aio:
                print(f"NO AIO  {query!r}  (page_token follow-up empty)")
                print()
                continue

        print_references(query, aio)
        print()


if __name__ == "__main__":
    main()

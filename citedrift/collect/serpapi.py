"""SerpApi adapter. Stdlib HTTP. One retry on network / HTTP 5xx only."""

from __future__ import annotations

import http.client
import json
import ssl
import time
import urllib.parse

SEARCH_URL = "https://serpapi.com/search"
SEARCH_CAP = 30
RETRY_WAIT_S = 5
CONNECT_TIMEOUT_S = 30
READ_TIMEOUT_S = 60

LOCATION = "Austin, Texas, United States"
HL = "en"
GL = "us"
NO_CACHE = True


class SearchCapExceeded(Exception):
    """Next SerpApi call would exceed SEARCH_CAP."""


def _https_get(host: str, path: str) -> tuple[int, str]:
    context = ssl.create_default_context()
    conn = http.client.HTTPSConnection(
        host, 443, timeout=CONNECT_TIMEOUT_S, context=context
    )
    try:
        conn.connect()
        if conn.sock is not None:
            conn.sock.settimeout(READ_TIMEOUT_S)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body
    finally:
        conn.close()


class SerpApiAdapter:
    def __init__(self, api_key: str, *, search_cap: int = SEARCH_CAP) -> None:
        self.api_key = api_key
        self.search_cap = search_cap
        self.searches_used = 0

    def remaining(self) -> int:
        return self.search_cap - self.searches_used

    def google_search(self, query: str) -> dict:
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "location": LOCATION,
            "hl": HL,
            "gl": GL,
            "no_cache": "true" if NO_CACHE else "false",
        }
        return self._get(params, retry=True)

    def google_ai_overview(self, page_token: str) -> dict:
        params = {
            "engine": "google_ai_overview",
            "page_token": page_token,
            "api_key": self.api_key,
            "no_cache": "true" if NO_CACHE else "false",
        }
        return self._get(params, retry=False)

    def _get(self, params: dict[str, str], *, retry: bool) -> dict:
        self.searches_used += 1
        parsed = urllib.parse.urlparse(SEARCH_URL + "?" + urllib.parse.urlencode(params))
        host = parsed.hostname or "serpapi.com"
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        try:
            status, body = _https_get(host, path)
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            if retry:
                time.sleep(RETRY_WAIT_S)
                return self._get(params, retry=False)
            raise RuntimeError(f"network error from SerpApi: {exc}") from exc
        if 500 <= status <= 599:
            if retry:
                time.sleep(RETRY_WAIT_S)
                return self._get(params, retry=False)
            try:
                return json.loads(body)
            except json.JSONDecodeError as parse_exc:
                raise RuntimeError(f"HTTP {status} from SerpApi: {body[:500]}") from parse_exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as parse_exc:
            raise RuntimeError(f"HTTP {status} from SerpApi: {body[:500]}") from parse_exc

"""SerpApi adapter. Stdlib HTTP. One retry on network / HTTP 5xx only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

SEARCH_URL = "https://serpapi.com/search"
SEARCH_CAP = 30
RETRY_WAIT_S = 5

LOCATION = "Austin, Texas, United States"
HL = "en"
GL = "us"
NO_CACHE = True


class SearchCapExceeded(Exception):
    """Next SerpApi call would exceed SEARCH_CAP."""


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
        url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if retry and 500 <= exc.code <= 599:
                time.sleep(RETRY_WAIT_S)
                return self._get(params, retry=False)
            try:
                return json.loads(body)
            except json.JSONDecodeError as parse_exc:
                raise RuntimeError(f"HTTP {exc.code} from SerpApi: {body[:500]}") from parse_exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if retry:
                time.sleep(RETRY_WAIT_S)
                return self._get(params, retry=False)
            raise RuntimeError(f"network error from SerpApi: {exc}") from exc

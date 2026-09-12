"""Syntactic URL canonicalization. No HTTP. Rules 1–7 and 9 only."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

TRACKING_EXACT = frozenset({"gclid", "fbclid", "msclkid", "ref", "source", "mc_cid"})
DROP_AMP_QUERY = ("amp", "1")

# ISO 3166-1 alpha-2 except US; .io is commercial per spec.
_US = "us"
_IO = "io"


def is_resolvable(url: str) -> bool:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path or ""
    return not (host == "google.com" and path.startswith("/goto"))


def registrable_domain(url: str) -> str:
    ext = EXTRACT(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    if ext.suffix:
        return ext.suffix.lower()
    return (ext.domain or "").lower()


def tld_class(url: str) -> str:
    suffix = (EXTRACT(url).suffix or "").lower()
    if suffix in {"gov", "mil"}:
        return "gov"
    if suffix == "edu":
        return "edu"
    if suffix == "org":
        return "org"
    last = suffix.rsplit(".", 1)[-1]
    if suffix in {"com", "net", "io"} or last == "io":
        return "com"
    if len(last) == 2 and last != _US:
        return "intl"
    if suffix and last != _US:
        return "com"
    return "other"


def _drop_tracking(query: str) -> list[tuple[str, str]]:
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lower = key.lower()
        if lower.startswith("utm_") or lower in TRACKING_EXACT:
            continue
        kept.append((key, value))
    return kept


def _drop_amp_query(params: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [kv for kv in params if not (kv[0].lower() == "amp" and kv[1] == "1")]


def _drop_amp_path(path: str) -> str:
    segs = [s for s in path.split("/") if s.lower() != "amp"]
    out = "/".join(segs)
    if path.startswith("/") and not out.startswith("/"):
        out = "/" + out
    return out or "/"


def canonicalize(url: str) -> str:
    raw = url.strip()
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        port = None

    params = _drop_tracking(parts.query)
    fragment = ""  # rule 6: strip; content-anchor exceptions deferred

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    if host.startswith("amp."):
        host = host[4:]
    path = _drop_amp_path(path)
    params = _drop_amp_query(params)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    netloc = host if port is None else f"{host}:{port}"
    query = urlencode(params, doseq=True)
    return urlunsplit((scheme, netloc, path, query, fragment))

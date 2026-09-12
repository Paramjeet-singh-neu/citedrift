# Decisions

Append-only. Agent writes; human reads.

Format: `date | decision | alternatives considered | reversible? y/n`

---

2026-09-11 | Runtime query config is `config/queries.json` (stdlib json). `config/queries.yaml` left untouched and is not read. | PyYAML dependency; keep YAML-only | y

2026-09-11 | Collector always sends `no_cache=true`. SerpApi caching would serve identical results for repeat queries within the hour and fabricate stability in the drift metric. | Allow cache / make no_cache configurable per run | y

2026-09-11 | Exactly one retry, 5s wait, only on network error or HTTP 5xx, only on the main Google search. No retry on 4xx. No retry on `google_ai_overview` because page_token expires in ~60s. Retries count toward the 30-search cap. | Retry expanded call; exponential backoff; retry 4xx | y

2026-09-11 | Search cap abort does not write manifest rows for queries never attempted. If the cap blocks the expanded call after `_main.json` is written, that query gets a manifest row with `error=aborted_search_cap` and remaining queries are skipped. | Write placeholder rows for unfetched queries | y

2026-09-11 | Cap is checked before each query: remaining searches must be >= 2 (main + possible expand). No per-call abort after a query starts, so we never spend a main search then skip expand. A 5xx retry on a query started with remaining==2 can still use a third search. | Per-call cap; reserve 3 to cover retry | y

2026-09-11 | `delivery_mode=expanded` only if the second call returned references. Token present but expand failed or empty → `delivery_mode=none` plus `error`. `aio_present=true` and `reference_count=0` always has `error` set (`aio_without_references` or `expanded_aio_empty`). | Treat token-only as expanded; allow empty AIO with no error | y

2026-09-11 | Deleted `config/queries.yaml`. `config/queries.json` is the only query source of truth. | Keep both files | n

2026-09-11 | `aio_present` is whether the MAIN response had a top-level `ai_overview`. Expand timeout/failure leaves `aio_present=true`. New field `aio_complete` is true only when a reference list was obtained. Analysis must drop `aio_complete=false` rather than treat them as zero-AIO. Runs before this fix have an unreliable `aio_present` field — do not backfill. | Keep counting timed-out expands as no-AIO | n

2026-09-11 | SerpApi HTTP uses stdlib `http.client`: 30s connect, 60s read. Main call still retries once on timeout/network/5xx. Expanded call does not retry (page_token ~60s). `CITEDRIFT_RUNNER` manifest field: `actions` in GHA, else `local`. | Single urlopen timeout; retry expand | y


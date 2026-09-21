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

2026-09-11 | Parser `aio_complete` when the field is missing: derive as (`error` is null AND `reference_count` > 0). Record `aio_complete_source`=`field`|`derived`. Do not assume missing means complete or incomplete. | Skip all pre-fix rows; treat missing as complete | y

2026-09-11 | FROZEN answer-text join (any change invalidates stored hashes): walk `text_blocks` in order; paragraph/heading use `snippet`; list uses each item's `snippet` one per line; ignore other block types with a warning naming the type; join with a single newline; strip leading/trailing whitespace on the final string only; sha256 UTF-8. Nested list items are not walked. | HTML-ish join; include table/expand blocks | n

2026-09-11 | Inline citation keep: if even-length list, first half untitled, second half titled, links pairwise equal → keep second half. Else keep items that have `title`; if none, keep the original list. Expanded lists are kept as-is. | Drop untitled by key only without link check | y

2026-09-12 | Normalizer is syntactic only: rules 1–7 and 9. Redirect-following (8) and rel=canonical (10) are deferred. The titled reference block already yields real URLs; fetching would make normalization non-deterministic and slow. Fragments are stripped with no content-anchor exceptions yet. | Fetch redirects/canonical now | y

2026-09-12 | Identity is two fields: `tld_class` (mechanical from suffix: gov/edu/org/com/intl/other) and `source_class` (human map in `config/source_classes.json`, default unclassified). tld_class is reproducible; source_class is a judgment call and must be auditable in config, not hardcoded. Agent must not add map entries. | Single domain_type enum; infer class from hostname | n

2026-09-12 | tldextract uses the bundled PSL (`suffix_list_urls=()`), no live PSL fetch. Unknown query params are kept (only listed tracking keys are dropped) so we do not over-normalize. | Live PSL updates; drop unknown params | y

2026-09-12 | Jaccard empty pairs store `null` plus `jaccard_note`=`both_empty` or `union_empty`. Nulls are omitted from `values` and counted in `n_null_excluded`. A 0 would look like total churn; a 1 like perfect stability. | Store 0; store 1; drop the pair | y

2026-09-12 | AIO presence denominator is `data/raw/*/manifest.jsonl`, not `answers.jsonl`. Incomplete rows split into `runs_failed_fetch` (error set) and `runs_genuine_absence` (error null, not complete); those counts are never added into one missing field. Presence rate is complete/attempted. | Denominator = answers.jsonl; lump incomplete | n

2026-09-12 | RBO is Webber, Moffat, Zobel 2010 eq. 32 (extrapolated), p=0.9. Domain lists are unique registered domains in first-citation order. Both-empty lists → `null` + `rbo_note=both_empty`, excluded like Jaccard. A shorter list that is a prefix of a longer list scores 1.0 — that is the extrapolation, not a bug. | rbo_min only; include duplicate domains | y

2026-09-12 | Source survival uses complete observations only, ordered by fetched_at; k is lag in that sequence (failed fetches are not a zero-citation run). Computed for `url_canonical` and `domain`. Empty run N contributes no instances. | Lag across all attempts; URL only | y

2026-09-12 | `make analyze` writes `data/analysis/metrics.json` (rebuild each run). `make drift` is an alias. | `make drift` only, matching AGENTS.md naming | y

2026-09-12 | Report is stdlib HTML + inline SVG. No Jinja2, matplotlib, or plotly. PROPOSAL §12 stack table (Jinja2 + matplotlib/plotly) is superseded for this deliverable: the report is one file:// page, those libraries are not in pyproject.toml, and adding them is a stop-gate. | Add Jinja2/plotly | y

2026-09-12 | Report copy is numbers and method/limitations facts only. Section 4 RBO is labelled "Citation stability by audience" with values grouped by audience; no claim sentence. Locale and cadence are labelled configuration (collector constants + workflow cron). Date range and run count are derived from fetched_at / run_id in metrics.json. | Interpret HCP movement in the report | n

2026-09-12 | Report: one consecutive-pair table (audience + interval_minutes + Jaccard/RBO url and domain). Patient-only journey-stage table is treatment minus by_audience HCP, not a recrawl of citations. Display column `complete_fetch_rate` reads `presence_rate` from metrics.json. | Keep four pair tables; recompute patient composition from citations | y

2026-09-12 | README headline and report intro copy are the human-authored text inserted verbatim. Agent does not rewrite findings. | Summarize or tighten the copy | n

2026-09-12 | Daily collect workflow rebuilds parse/normalize/analyze/report and commits `data` plus `docs/index.html`, not only `data/raw`. CI pip-installs `requests` and `tldextract`; `requests` is not a pyproject dependency (collector uses stdlib HTTP). | Keep raw-only commit; `pip install -e .` | y

2026-09-13 | README replaced with human-authored copy (headline, report link, findings, limitations, pipeline). Agent does not rewrite findings. | Keep prior two-paragraph README | n

2026-09-13 | Human classified 14 previously unclassified domains in `config/source_classes.json`. `ucdavis.edu` is `health_system`, not academic. New class `insurer` (`uhc.com`, `primetherapeutics.com`). | Treat ucdavis.edu as academic; fold insurers into commerce | n

2026-09-13 | Report intro scope sentence derives run count (unique `run_id`), `n_citations`, date range, and window hours from metrics.json min/max `fetched_at`. Same-day range stays "on {day}"; multi-day uses "from … to …". Query count, conditions, locale, and all other intro paragraphs stay as written. | Keep hardcoded 3 runs / 273 / 1.4 hours | y

2026-09-13 | README sample line and "What it found so far" replaced with human-authored 5-run copy. Limitations section unchanged. | Also rewrite limitations and report intro findings | n

2026-09-13 | Report intro findings replaced with human-authored 5-run paragraphs (59 of 60, academic 37.5% / 0 of 150, YouTube 68). Scope sentence still derived from metrics.json. Stability and source-category paragraphs unchanged. | Also rewrite the 19-of-23 stability sentence | y

2026-09-13 | Report intro stability paragraph replaced with human-authored short-vs-long interval copy. Agent does not rewrite findings. | Keep 19-of-23 sentence | n

2026-09-13 | Report intro: YouTube line is "13 of those 68 appear in the top three." Stability is 15 of 16 short-interval pairs identical (33–47 min); long-interval movement described per query class. Replaced because prior copy contradicted the pair table (t2d_diagnosis 0.4000 at 35.7 min; htn_symptoms 0.2500 at 784.9 min). | Write 19.1%; keep prior stability paragraph | n

2026-09-13 | Intro lead is "Four things stand out". Limitations "One day" replaced by derived "N calendar dates, hours, runs" plus derived clinician n (queries, complete observations, top-three). Section 6 adds human-authored Jardiance/Opsumit sentence. | Drop the stand-out sentence; hardcode 23.2 / 5 | y

2026-09-15 | Report intro stability is 15 of 18 pairs at 34–47 min (bound 34.0–47.3 excludes 33.6–33.7 and t2d_hcp 81.8). Section 6 manufacturer copy is 7-run Jardiance/Opsumit/losartan. | Keep 5-run manufacturer sentence | n

2026-09-15 | Intro remaining 5-run sentences replaced with 7-run counts: 83 of 84 presence; academic 33.3% / 0 of 210 / 12 patient all-positions; health-system 29.5% patient top-three and none of 36 clinician top-three (twice at lower positions); YouTube 98 / 17 top-three, Mayo 55, NIH 45, societies 19. Short-interval exceptions wording is one diagnosis query plus both pairs from one clinician query. | Leave Mayo/NIH at 38/33; keep health-system “absent at any position” | n

2026-09-15 | Human classified 4 domains: `diabetes.org.uk` advocacy, `medicinenet.com` and `news-medical.net` consumer_health, `uspharmacist.com` clinical_reference. | Leave unclassified | n

2026-09-15 | Intro: “were the reverse” → “ran the other way” (health-system is not a mirror of academic). Clinician Jaccard floor written 0.067 (table 0.0667), not 0.07. README and portfolio snapshot `citedrift.html` brought to the 7-run copy. Checking intro against tables in this round caught the reverse, the rounding, two stale published copies, and the false “both PAH queries unchanged.” | Keep 0.07; keep “the reverse” | n

2026-09-21 | Human classified 15 domains: `tandfonline.com` academic; `escardio.org` professional_society; `fda.gov`, `poison.org`, `safetyandquality.gov.au`, `hse.ie` gov_health; `beyondtype1.org`, `texasheart.org` advocacy; `pahinitiative.com` manufacturer; `providence.org`, `froedtert.com`, `pennmedicine.org`, `uchealth.com` health_system; `renalandurologynews.com` clinical_reference; `mytherapyapp.com` commerce. Left unclassified: `utah.edu`, `chop.edu`. | Invent classes for utah.edu / chop.edu | n

2026-09-21 | Human classified `utah.edu` and `chop.edu` as `health_system` (Utah Health / CHOP condition pages). | academic for .edu | n

2026-09-21 | Human reclassified `harvard.edu` from academic to `consumer_health` (Harvard Health Publishing patient pages, not journals). | Keep academic | n

2026-09-21 | 12-run intro: presence 141 of 144; academic 23.3% HCP all-positions / 0 of 889 patient; health-system 26.4% patient / 0 of 63 HCP top-three; delivery 117/119 vs 21/21; YouTube 30/176; societies 22 / 0 top-three; short-interval 15 of 18; t2d_treatment 11-set then drop 8 then drop 3 add 6. Scope close is “begin characterising how it changes day to day.” Limitations add HCP confounding (drug-class comparison). Section 6 is 11 of 12 / all 12 Opsumit 3-2-3. README synced to the same 12-run copy. | Keep 7-run intro; write “replaced 6 of 8” | n


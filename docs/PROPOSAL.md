# CiteDrift — Project Proposal & Build Plan

**Thesis:** AI Overview citation sets for the same query are not stable. Every AI visibility report sold today is a single sample from a distribution nobody has measured. This project measures the distribution, then adds a grounding layer that checks what those AI answers actually claim against the FDA drug label.

**Two audiences, one codebase:**
- **Phase A** → the artifact sent to Sosemo. Pipeline + preliminary drift finding.
- **Phase B** → the portfolio thesis. Claim extraction + label grounding + eval harness.

Phase B ships in the repo and the writeup. It does not go in the first email.

---

## 1. What this is and what it deliberately is not

**Is:**
- A config-driven measurement pipeline that replicates a published research methodology and extends it along the time axis
- A grounding layer that classifies factual claims against authoritative source text, with an abstain path
- An eval harness with a labeled adversarial set

**Is not** (state these in the README — knowing what you didn't build is a production signal):
- Multi-tenant. No auth, no orgs, no client management.
- A rank tracker. Organic rank is an enrichment field, not the product.
- A medical accuracy tool. Phase B *flags claims for human review*. That phrasing is load-bearing and appears in the README, the UI, and every conversation about it.
- A Profound/Scrunch competitor. If you catch yourself building a client dashboard, stop.

---

## 2. Phase gates

Gates are pass/fail. Do not proceed on a failed gate — replan.

### Phase 0 — Extraction spike (2–4 hours, tonight)
The whole project rests on one unverified assumption: that you can reliably retrieve AI Overview *source blocks* for a given query.

- Pick 5 queries. Hit your SERP provider 3× each, spaced 30+ minutes.
- Record: did an AIO fire? were cited sources returned? how many? in order?

**Gate:** AIO presence ≥ 60% of calls AND source URLs returned with position. If the provider returns the AIO text but not the source list, that provider is useless here — switch before writing anything else.

**If the gate fails:** fall back to the internal-link opportunity finder. Same day. Do not spend two days fighting extraction.

### Phase 0.5 — Collection script (1 hour, tonight, after the gate)
Crudest possible thing that works:

```
for query in query_set:
    resp = serp.fetch(query, engine, locale)
    write_json(f"raw/{run_id}/{query_hash}.json", resp)
```

Cron it 2×/day. Never touch the raw files again except to read them. Raw JSON on disk is your only irreplaceable asset.

### Phase A — Engine (days 1–3, ship Tuesday)
**Gate:** static HTML report renders with a drift number and a domain-vs-URL decomposition.

### Phase B — Grounding (days 4–8)
**Gate:** false-supported rate on the adversarial eval set is measured and reported, whatever it is.

### Phase C — Harden + write up (days 9–12)
**Gate:** clean clone → `make run` → report, on a machine that isn't yours.

---

## 3. Query set design

Mirror Sosemo's *structure* at 1/4 the volume. Their method: 10 conditions × (4 journey stages + HCP + rare disease).

Yours: **2 conditions × 6 categories = 12 queries.** Optionally 18 with a third condition.

**Condition selection matters.** Pick one commercially contested and one boring:
- **Diabetes** — huge volume, contested, GLP-1 branded drugs with rich DailyMed labels
- **Hypertension** — high volume, commercially dull, generic-dominated (lisinopril, losartan)

The contrast is itself a finding. If drift is high in diabetes and low in hypertension, the story is that instability tracks commercial contest, and that's an actionable strategic claim.

Both conditions must have branded drugs with retrievable SPL labels, because Phase B reuses this query set.

Schema for each query:

```yaml
- text: "what are the early signs of type 2 diabetes"
  condition: diabetes
  journey_stage: symptoms        # symptoms|diagnosis|treatment|branded
  audience: patient              # patient|hcp|rare_disease
  target_drug: null              # populated for branded queries → Phase B
```

---

## 4. Architecture

```
config/queries.yaml
        │
        ▼
  ┌───────────────┐
  │  Collector    │  SERP adapter (swappable), retry/backoff, run_id stamping
  └───────┬───────┘
          │  raw JSON, append-only
          ▼
  ┌───────────────┐
  │  Parser       │  AIO detection → answer text + ordered citation list
  └───────┬───────┘
          ▼
  ┌───────────────┐
  │  Normalizer   │  ◄── THE LOAD-BEARING COMPONENT
  └───────┬───────┘
          ▼
  ┌───────────────┐
  │  Enricher     │  domain type, publish/modified date, organic rank,
  │               │  keyword density, journey-stage coverage, link graph
  └───────┬───────┘
          ▼
     DuckDB + Parquet
          │
          ├──► Drift analyzer ──► static HTML report      [PHASE A]
          │
          └──► Claim extractor ──► Label grounder ──► verdict queue  [PHASE B]
                                        ▲
                                   DailyMed SPL cache
```

### The normalizer is where this project succeeds or fails
Your drift metric is a set comparison over URLs. Every un-canonicalized URL variant registers as fake churn and your headline number becomes garbage.

Must handle:
- Strip tracking params (utm_*, gclid, fbclid, ref, source)
- Trailing slash, case in path, default ports
- `www.` vs bare host
- Follow redirects to final URL (cache aggressively — this is your slowest step)
- AMP variants → canonical (`/amp/`, `?amp=1`, `amp.` subdomain)
- Respect `<link rel="canonical">` when fetched
- Fragment removal, but preserve meaningful query params (`?id=`, `?article=`)

Write unit tests for this before you write the drift analyzer. Ten test cases minimum. This is the component an interviewer will poke at if they're any good, and it's the one that proves you've shipped before.

---

## 5. Data model

```sql
-- one execution of the full query set
run(run_id PK, started_at, engine, locale, provider, config_hash)

-- one query in one run
observation(
  obs_id PK, run_id FK, query_id,
  aio_fired BOOL, answer_text, answer_hash,
  raw_path, fetched_at
)

-- normalized page, deduped globally
source(
  source_id PK, url_canonical UNIQUE, url_raw_first_seen,
  domain, domain_type,          -- gov|org|edu|com|other
  publisher, published_at, modified_at,
  first_seen_run, last_seen_run
)

-- the edge that drift is computed over
citation(obs_id FK, source_id FK, position INT, PRIMARY KEY(obs_id, source_id))

-- Sosemo's Phase 2 enrichment fields
source_metrics(
  source_id FK, query_id, run_id,
  organic_rank INT NULL, keyword_density FLOAT,
  journey_coverage TEXT[],      -- which stages the page addresses
  measured_at
)

-- link graph
link_edge(from_source_id, to_source_id, edge_type)  -- internal|external

-- PHASE B
claim(
  claim_id PK, obs_id FK, verbatim_span, claim_text,
  claim_type,                   -- indication|dosage|contraindication|adverse_event|efficacy|mechanism
  subject_drug, extracted_at, extractor_version
)

verdict(
  claim_id FK, label_setid, label_section_loinc, evidence_span,
  classification,               -- supported|unsupported|contradicted|out_of_scope|abstained
  confidence FLOAT, model_version, decided_at
)
```

Two design notes worth saying out loud in an interview:
- `answer_hash` lets you detect answer-text drift independently of citation drift. They move differently. Text can change while sources hold, and vice versa.
- `citation` is the fact table. Everything else is dimension. Keeping it that clean is why the drift queries are one-liners.

---

## 6. Drift metrics — defined, not hand-waved

The headline needs a defensible definition. Report all five.

**1. AIO presence rate**
`P(aio_fired) per query across runs`
If this is 65% rather than 100%, that alone is a finding: a single-sample audit has a one-in-three chance of seeing nothing.

**2. Citation set churn — Jaccard**
Between consecutive runs for the same query:
`J = |A ∩ B| / |A ∪ B|` over canonical URLs.
Report the distribution, not the mean. The mean hides bimodality.

**3. Order churn — RBO (rank-biased overlap)**
Top-weighted, handles unequal-length lists, correct tool for ranked citation lists. Use p=0.9. Say "RBO" not "Jaccard" when you want to sound like you've read the retrieval literature — and be ready to explain why top-weighting matters here (position 1 gets the click).

**4. Source survival curve**
For a source appearing in run *N*, `P(still cited at N+k)` for k = 1..K. The most legible chart in the whole report. Needs ~14+ runs to be meaningful, so this is the 30-day-version deliverable, not the Tuesday one.

**5. Domain-level vs URL-level drift — the actual insight**
Compute 2 and 3 twice: once over canonical URLs, once over registered domains.

The decomposition is the finding:

| URL churn | Domain churn | Strategic implication |
|---|---|---|
| High | Low | Google swaps pages *within* a stable trusted set. Optimize the whole topical cluster, not one page. Domain authority is the moat. |
| High | High | The source pool itself is unstable. Single-snapshot audits are near-worthless; only longitudinal measurement is defensible. |
| Low | Low | Citations are stable, and one-time audits are fine. (Would falsify the project thesis — report it honestly if that's what you find.) |

Pre-commit to reporting whichever cell you land in, including the one that kills the thesis. Say that in the README. It's the difference between research and marketing.

---

## 7. Phase B — the grounding layer

### 7.1 Claim extraction
LLM with strict structured output. Non-negotiable constraint: **every claim must carry a verbatim span from the answer text.** Reject any claim whose span isn't a substring of `answer_text`. Without this you get hallucinated claims about hallucinations, which is a genuinely funny bug and a fatal one.

```json
{
  "claims": [{
    "verbatim_span": "exact substring from answer_text",
    "claim_text": "normalized restatement",
    "claim_type": "dosage",
    "subject_drug": "metformin",
    "is_factual_assertion": true
  }]
}
```

Drop anything with `is_factual_assertion: false` (hedges, "talk to your doctor", general advice).

### 7.2 Ground truth: DailyMed SPL
Free public API, stable, returns FDA structured product labels as XML with LOINC-coded sections.

**Route by claim type instead of searching the whole label.** This is the design choice that shows domain thinking:

| claim_type | LOINC section |
|---|---|
| indication | 34067-9 Indications & Usage |
| dosage | 34068-7 Dosage & Administration |
| contraindication | 34070-3 Contraindications |
| adverse_event | 34084-4 Adverse Reactions |
| efficacy | 34092-7 Clinical Studies |
| mechanism | 34090-1 Clinical Pharmacology |

Cache labels locally by `setid`. They change rarely; refetch monthly.

### 7.3 Retrieval within section
**Try BM25 before embeddings.** Label language is formulaic and repetitive; lexical matching often beats dense retrieval here, it's cheaper, and it's far easier to explain why a given passage was retrieved. If BM25 wins, that result is itself a talking point — most candidates reach for embeddings reflexively.

Measure both. Report the comparison.

### 7.4 Verdict + the abstain path
```
supported     — label section directly affirms the claim
contradicted  — label section directly conflicts with it
unsupported   — relevant section retrieved, claim not addressed
out_of_scope  — claim isn't a label-checkable assertion
abstained     — retrieval confidence below threshold, no verdict rendered
```

**The abstain path is the whole point.** The system never renders a verdict it cannot ground to a specific label span. Below threshold → route to human queue with the retrieved candidates attached.

This is the same shape as the confidence-gated routing in the Acuvate complaint pipeline where the model never closed a case, and the same shape as CoachCheck grounding claims to a frame and timestamp. Three domains, one pattern. That continuity is the portfolio thesis — make it explicit in the writeup.

---

## 8. Eval design

This is what separates the project from a demo. Build the set by hand.

**50 claims, four buckets:**

| Bucket | n | Construction |
|---|---|---|
| True-supported | 15 | Paraphrased directly from label sections |
| Contradicted | 15 | Mutate a real label fact: change a dose, flip a contraindication, invent an indication |
| Out-of-scope | 10 | Real AIO sentences that aren't label-checkable |
| Adversarial near-miss | 10 | Right drug wrong population; right dose wrong frequency; label-adjacent but not stated |

**Report:**
- Precision/recall per class
- **False-supported rate** — the only metric that matters for safety. A system that calls a contradicted claim "supported" is the failure that kills the product. Report it first.
- Abstention rate, and precision on non-abstained decisions
- BM25 vs embedding retrieval, side by side

The 10 adversarial cases are the ones worth talking about. Same discipline as the 12-case War Room adversarial set — say that connection out loud.

---

## 9. Stack, with rationale

Every choice needs a one-line defense, because "why not X" is the interview question.

| Component | Choice | Why (and why not the obvious alternative) |
|---|---|---|
| Language | Python 3.11+ | — |
| SERP | DataForSEO or SerpApi, behind an adapter interface | Licensed access. Headless Google scraping violates ToS and is a bad look in a repo you send to a search agency. Adapter because provider reliability is risk #1. |
| Storage | DuckDB + Parquet | Single-file analytical store, zero infra, fast on this volume. Postgres adds ops burden for no benefit at 10⁴ rows. |
| Orchestration | APScheduler or cron | Airflow at this scale is resume padding and reads as such. Say so if asked. |
| LLM structured output | Native JSON schema mode or Instructor | Schema validation at the boundary, not regex on prose. |
| Label retrieval | BM25 (rank_bm25) first, embeddings as comparison | See 7.3. Measure, don't assume. |
| Tracing | W&B Weave, or structured JSONL | Weave gives continuity with War Room. JSONL is fine and has zero setup. |
| Report | Static HTML (Jinja2 + matplotlib/plotly to inline SVG) | **Not Streamlit for the send.** Nobody at a 10-person agency will clone a repo and pip install. A single self-contained HTML file opens in a browser from an email. Streamlit optional for the portfolio version. |

---

## 10. Cost

| Item | Estimate |
|---|---|
| SERP calls: 18 queries × 2/day × 30 days × 1 engine | ~1,080 calls |
| SERP provider | $50–75 one month |
| LLM: claim extraction + verdicts, ~2k claims | $10–25 |
| DailyMed | Free |
| **Total** | **Under $100** |

Set a hard spend cap in code. A retry loop against a paid SERP endpoint is the classic way to turn $50 into $500 overnight.

---

## 11. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | AIO source extraction unreliable | **Fatal** | Phase 0 gate tonight. Fall back to internal-link finder same day. |
| 2 | Not enough elapsed time for a drift signal by Tuesday | High | Start collecting tonight. Frame Tuesday's number as preliminary; 30-day version becomes the September follow-up. |
| 3 | URL normalization inflates drift | High | Unit tests before the analyzer. Report drift both raw and canonical to show the delta. |
| 4 | Phase B reads as a medical claim | High | "Flags claims for human review" everywhere. Abstain path prominent. Well-known non-controversial drugs only. Not in the first email. |
| 5 | Scope creep into a visibility dashboard | Medium | Guardrails in §1. No auth, no tenancy, no client CRUD. |
| 6 | SERP provider ToS / scraping optics | Medium | Licensed API only. State it in the README. |
| 7 | Findings contradict the thesis | Low | Pre-commit to publishing whatever you find. Honest null results are more credible than convenient ones. |

---

## 12. Deliverables

**End of Phase A (Tuesday):**
1. `citedrift/` — collector, parser, normalizer, enricher, analyzer
2. `report.html` — self-contained, opens in a browser: AIO presence rate, Jaccard/RBO distributions, domain-vs-URL decomposition, one chart per finding
3. README leading with the *finding*, not the stack
4. Raw JSON archive, still accumulating

**End of Phase B (day 8):**
5. Claim extractor + label grounder + abstain routing
6. `evals/` — 50-case labeled set, runner, results table
7. Human review queue (a table with links to label spans is enough)

**End of Phase C (day 12):**
8. `make run` works on a clean clone
9. Writeup: the three-domain grounding thesis (video frames → label sections → incident evidence)
10. Deferred-work section in the README

---

## 13. Deliberately deferred — put this in the README

Listing what you didn't build is a production signal. It says you scoped rather than ran out of time.

- Multi-engine parity (Bing, AI Mode, ChatGPT, Perplexity) — adapter interface exists, only Google implemented
- Locale/geo variation — AIOs differ by location; single locale here
- Multi-tenancy, auth, client management
- Backfill of historical AIO data (not available from any provider)
- Human review UI beyond a table
- Automated label-change monitoring
- Statistical significance testing on drift differences between conditions (n too small)

---

## 14. Writeup discipline

README first line is the finding. Not the stack.

> Citation sets for the same healthcare query change X% run over run, while the *domains* cited change only Y%. Single-snapshot AI visibility audits are sampling from a distribution nobody measures.

Nobody reads "Built with Python, DuckDB, and DataForSEO." Put that in a collapsed section near the bottom.

---

## 15. The Sosemo send package

Separate from the repo. Assembled Tuesday.

- **One self-contained `report.html`** (or a 90-second Loom if the charts need narration)
- **Three sentences of email.** Framed as an experiment on their published Phase 2 methodology, not as something built for them.
- **One link** to the repo
- **One ask:** 20 minutes with Ken. Not "let me know your thoughts."
- **No Phase B.** Not mentioned, not linked, not hinted at.
- **The hook for contact #2:** the pipeline is still running and will have a 30-day dataset by mid-September.

Do not attach a deck. Do not write more than three sentences. The report is the argument.

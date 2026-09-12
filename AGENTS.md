# CiteDrift

Measures whether Google AI Overview citation sets are stable over time for the
same query, then grounds factual claims in those answers against FDA drug labels.

Full spec: `docs/PROPOSAL.md`. Read it before planning any task. Re-read the
specific section named in the task before implementing.

## Working agreement

I am the sole reviewer and I review every non-trivial change. Your job is to
implement against the spec, not to improve the spec.

**Before starting any task**, post a plan: ≤5 bullets, naming which PROPOSAL
section it implements and which files you'll touch. Wait for my go.

**After finishing any task**, post this exact format:

    CHANGED:    files touched, one line each
    DECISIONS:  choices I made that weren't in the spec, and why
    ASSUMED:    anything I filled in without being told
    UNVERIFIED: what I have NOT tested or confirmed
    NEXT:       the one thing that should happen next

**Append every non-trivial decision** to `docs/DECISIONS.md`:
`date | decision | alternatives considered | reversible? y/n`

**If the spec is wrong, silent, or ambiguous** — say so and stop. Do not
resolve it yourself. A wrong guess that compiles is worse than a question.

## Commands

    make collect     # one collection run
    make parse       # raw JSON -> data/parsed/*.jsonl
    make drift       # compute metrics
    make report      # build report.html
    make test
    make eval        # Phase B only

## Architecture

    citedrift/
      collect/     SERP adapters. Provider-swappable behind one interface.
      parse/       AIO detection, citation extraction
      normalize/   URL canonicalization  <-- highest-risk component
      enrich/      domain type, dates, organic rank, link graph
      analyze/     drift metrics
      ground/      Phase B: claim extraction, label retrieval, verdicts
      report/      Jinja2 -> single self-contained HTML
    data/raw/      append-only SERP JSON. NEVER modify or delete.
    evals/         labeled test set + runner
    docs/

## Hard rules

- `data/raw/` is append-only. Never edit, delete, reformat, or "clean" it.
- Licensed SERP API only. No headless browser scraping of Google, ever.
- No agent frameworks (LangChain, LlamaIndex, CrewAI). Plain SDK calls.
- No auth, no multi-tenancy, no client management, no CRUD dashboard.
  If a task seems to need one, that's scope creep — stop and ask.
- Hard spend cap enforced in code before any paid API loop.
- Phase B language is "flags claims for human review." Never "verifies,"
  "confirms," "validates," or "checks accuracy" — not in code, comments,
  docstrings, UI strings, or the README.
- Python 3.11+, type hints, pytest. Boring code over clever code.

## Phase gates

Phase A (engine) must ship before Phase B (grounding) starts. Do not begin
Phase B work, scaffolding, or dependencies until I say Phase A is done.

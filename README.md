# CiteDrift

Measures which sources Google's AI Overview cites for healthcare
queries, and whether those sources hold steady over time.

**[View the report →](https://paramjeetsingh.me/citedrift.html)**

## What this is

12 queries across type 2 diabetes, hypertension, and pulmonary
arterial hypertension, spanning four journey stages (symptoms,
diagnosis, treatment, branded) and two audiences (patient-phrased and
clinician-phrased). Collected daily via GitHub Actions, one locale
(Austin, TX), Google only.

Current sample: 3 runs, 273 citations, 12 September 2026, spanning
1.4 hours.

## What it found so far

**AI Overviews were present every time.** 36 of 36 attempts returned
one, zero genuine absences. The single incomplete record was a network
timeout on the collector's side, logged separately rather than counted
as an absence.

**What gets cited first depends on how the question is phrased.**
Across the top three cited positions, academic sources were 53% of
citations on clinician-phrased queries and 0 of 90 on patient-phrased
ones. Health-system sites were the reverse: 30% of patient top-three
citations, absent from clinician results entirely. The two phrasings
also arrived through different delivery paths — all 30 patient
observations returned the AI Overview inline; all 5 clinician
observations required a second fetch.

**Being cited and being cited first are different things.** YouTube was
the most-cited domain at 46 citations, but only 17% landed in the top
three. Professional medical societies were cited 11 times and never
once in the top three. Commercial sites were the inverse: fewer
citations, 68% of them in the top three.

## Limitations

- 3 runs over 1.4 hours. Not enough to characterise change over time.
- The clinician-phrased findings rest on 2 queries, 3 run-pairs, and
  15 top-three citations.
- 3 conditions, one locale, one engine, one day.
- Source categories are a judgment call. The full mapping is in
  `config/source_classes.json` and open to disagreement.

## Pipeline

    collect    SerpApi -> raw JSON, append-only, never modified
    parse      raw -> citations.jsonl, answers.jsonl
    normalize  canonical URL, registrable domain, source class
    analyze    presence, Jaccard, RBO, survival, composition
    report     self-contained HTML, inline SVG, no external assets

Raw responses are committed as the audit trail. Everything downstream
is derived and rebuilt from scratch on each run.

## Running it

    make collect    # one collection run (needs SERPAPI_KEY)
    make parse
    make normalize
    make analyze
    make report
    make test

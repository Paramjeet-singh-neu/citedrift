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

Current sample: 7 runs, 630 citations, 12–15 September 2026, spanning
87.6 hours.

## What it found so far

**AI Overviews appeared on 83 of 84 attempts.** One genuine absence,
on a clinician-phrased query. One further record is a collector-side
network timeout, logged separately rather than counted as an absence.
Patient-phrased queries were complete on all 70 attempts; clinician-
phrased queries on 12 of 14.

**What gets cited first depends on how the question is phrased.**
Across the top three cited positions, academic sources were 33.3% of
citations on clinician-phrased queries and 0 of 210 on patient-phrased
ones. Academic sources are not absent from patient results — they
appear 12 times across all positions — but never near the top.
Health-system sites ran the other way: 29.5% of patient top-three
citations, and none of the 36 clinician top-three citations, though
they appear twice at lower positions.

**Being cited and being cited first are different things.** YouTube
was the most-cited domain at 98 citations, ahead of Mayo Clinic (55)
and NIH (45), but 17 of those 98 appear in the top three. Professional
medical societies were cited 19 times and never once in the top three.

**Citation sets were stable at short intervals and moved over hours.**
Within short intervals of 34–47 minutes, 15 of 18 pairs matched
exactly. The three exceptions were one patient diagnosis query and
both pairs from one clinician-phrased query. The two clinician-phrased
queries never matched on any pair, at any interval, falling as low as
0.067 Jaccard. Three queries were unchanged across all six of their
pairs: both treatment queries and the pulmonary arterial hypertension
symptoms query.

## Limitations

- 7 runs over 87.6 hours. Not enough to characterise change over time.
- The clinician-phrased findings rest on 2 queries, 12 complete
  observations, and 36 top-three citations.
- 3 conditions, one locale, one engine, four calendar dates.
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

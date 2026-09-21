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

Current sample: 12 runs, 1,082 citations, 12–20 September 2026,
spanning 207.0 hours.

## What it found so far

**AI Overviews appeared on 141 of 144 attempts.** Three genuine
absences — two on clinician-phrased queries, one on a patient
treatment query — plus one collector-side network timeout, logged
separately rather than counted as an absence. Patient-phrased queries
were complete on 119 of 120 attempts; clinician-phrased queries on
21 of 24.

**What gets cited depends on how the question is phrased.** Academic
sources — journals and research publishers — accounted for 23.3% of
citations on clinician-phrased queries and zero of 889 on
patient-phrased ones, at any position. Health-system sites ran the
other way: 26.4% of patient citations, and none of the 63
clinician-phrased top-three citations.

**Being cited and being cited first are different things.** YouTube
was the most-cited domain at 176 citations, ahead of Mayo Clinic (96)
and NIH (77), but 30 of those 176 reach the top three. Professional
medical societies were cited 22 times and never once in the first
three.

**Citation sets were stable at short intervals and moved over days.**
Within short intervals of 34–47 minutes, 15 of 18 pairs matched
exactly. Over roughly 24-hour intervals, both clinician-phrased
queries changed on every pair (floors 0.067 and 0.133). One treatment
query held an identical 11-source set across four days and six pairs,
then dropped 8 of those 11 in a single day, held the new 8-source set
for three more days, then dropped 3 of those 8 and added 6. Change
dates did not align across queries.

## Limitations

- 12 runs over 207.0 hours (9 calendar dates). Enough to describe
  what was cited and to begin characterising day-to-day change.
- The clinician-phrased findings rest on 2 queries, 21 complete
  observations, and 63 top-three citations. Both are drug-class
  comparison questions, so audience phrasing and question type are
  confounded in this set.
- 3 conditions, one locale, one engine.
- Source categories are a judgment call. `.edu` domains are classified
  by what the page is, checked by hand, not inferred from the suffix.
  The full mapping is in `config/source_classes.json` and open to
  disagreement.

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

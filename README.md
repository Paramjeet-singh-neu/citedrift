# CiteDrift measures which sources Google's AI Overview cites for healthcare queries, and whether those sources hold steady over time.

In a first 12-query sample across type 2 diabetes, hypertension, and pulmonary arterial hypertension, AI Overviews appeared on 36 of 36 attempts. What they cited first differed sharply depending on whether the question was phrased the way a patient asks it or the way a clinician does.

The tables and charts are in [`report/report.html`](report/report.html). It is self-contained and opens from a `file://` path with no network.

```
make collect    # one collection run (needs SERPAPI_KEY)
make parse
make normalize
make analyze
make report
make test
```

"""Source survival: P(cited at N+k | cited at N) for k = 1..K."""

from __future__ import annotations


def survival_curve(run_sets: list[set[str]]) -> dict[int, dict[str, float | int | None]]:
    n_runs = len(run_sets)
    out: dict[int, dict[str, float | int | None]] = {}
    for k in range(1, n_runs):
        survived = 0
        instances = 0
        pairs = 0
        for i in range(n_runs - k):
            start = run_sets[i]
            later = run_sets[i + k]
            if not start:
                continue
            pairs += 1
            for src in start:
                instances += 1
                if src in later:
                    survived += 1
        out[k] = {
            "rate": (survived / instances) if instances else None,
            "n_instances": instances,
            "n_pairs": pairs,
            "n_survived": survived,
        }
    return out

"""Statistics used in the write-up: Wilson intervals, and paired per-task differences with a
bootstrap interval over tasks and a sign-flip permutation p-value.

These functions are the same as in skill_ab/analyse.py, which produced the published numbers;
tests/test_stats.py checks that they reproduce results/summary.json.
"""
from __future__ import annotations

import math
import random
import statistics as st
from collections import defaultdict

BOOT = 10_000


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct(xs, q: float) -> float:
    """Linear-interpolated quantile."""
    xs = sorted(xs)
    if not xs:
        return math.nan
    i = (len(xs) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def paired_diff(runs: list[dict], cond: str, metric: str = "passed", seed: int = 1,
                baseline: str = "none", boot: int = BOOT) -> dict:
    """Mean over tasks of (mean `metric` under `cond` minus mean under `baseline`).

    The task, not the run, is the unit: repeats of one task are not independent samples. Returns the
    difference, a 95% bootstrap interval over tasks, a two-sided sign-flip permutation p-value over
    tasks, and how many tasks got better or worse. Empty dict if no task has both conditions.
    """
    by = defaultdict(lambda: defaultdict(list))
    for r in runs:
        by[r["task"]][r["condition"]].append(float(r[metric]))
    tasks = [t for t in by if by[t].get(cond) and by[t].get(baseline)]
    d = [st.mean(by[t][cond]) - st.mean(by[t][baseline]) for t in tasks]
    if not d:
        return {}
    rng = random.Random(seed)
    boots = sorted(st.mean(rng.choice(d) for _ in d) for _ in range(boot))
    obs = abs(st.mean(d))
    perm = sum(abs(st.mean(x * rng.choice((-1, 1)) for x in d)) >= obs - 1e-12 for _ in range(boot)) / boot
    return {"diff": st.mean(d), "ci": (pct(boots, 0.025), pct(boots, 0.975)), "p_perm": perm,
            "tasks": len(tasks), "tasks_better": sum(x > 0 for x in d), "tasks_worse": sum(x < 0 for x in d)}

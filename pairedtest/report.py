"""Summarise a runs file (one JSON object per run) into pass rates, paired differences against a
baseline condition, cost and skill loading, per model. Same definitions as skill_ab/analyse.py."""
from __future__ import annotations

import json
import math
import statistics as st
from collections import Counter
from pathlib import Path

from .stats import paired_diff, wilson


def load(path: str | Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def cell(rs: list[dict]) -> dict:
    n, k = len(rs), sum(bool(r["passed"]) for r in rs)
    cost = [r.get("cost_usd") or 0.0 for r in rs]
    return {"n": n, "passed": k, "pass_rate": k / n if n else math.nan, "wilson": wilson(k, n),
            "cost_mean": st.mean(cost) if rs else math.nan, "cost_total": sum(cost),
            "cost_per_pass": sum(cost) / k if k else None,
            "output_tokens_mean": st.mean(r["usage"]["output"] for r in rs) if rs else math.nan,
            "turns_mean": st.mean(r.get("num_turns") or 0 for r in rs) if rs else math.nan,
            "wall_median": st.median(r["wall_s"] for r in rs) if rs else math.nan,
            "skill_loaded_rate": sum(bool(r.get("skill_calls")) for r in rs) / n if n else math.nan,
            "failed_checks": dict(Counter(c["name"] for r in rs for c in r.get("checks", []) if not c["ok"]).most_common())}


def summarise(runs: list[dict], baseline: str = "none") -> dict:
    runs = [r for r in runs if "passed" in r]
    out = {"n_runs": len(runs), "baseline": baseline, "models": {}}
    for model in sorted({r["model"] for r in runs}):
        mr = [r for r in runs if r["model"] == model]
        conds = sorted({r["condition"] for r in mr}, key=lambda c: (c != baseline, c))
        fams = sorted({r["family"] for r in mr})
        m = out["models"][model] = {"conditions": {}, "families": {}, "paired": {}, "per_task": {}}
        for c in conds:
            rs = [r for r in mr if r["condition"] == c]
            m["conditions"][c] = cell(rs)
            m["families"][c] = {f: cell([r for r in rs if r["family"] == f]) for f in fams}
            if c != baseline:
                m["paired"][c] = {"all": paired_diff(mr, c, baseline=baseline),
                                  "cost_all": paired_diff(mr, c, "cost_usd", baseline=baseline),
                                  **{f: paired_diff([r for r in mr if r["family"] == f], c, baseline=baseline) for f in fams}}
        for t in sorted({r["task"] for r in mr}):
            m["per_task"][t] = {c: [sum(bool(r["passed"]) for r in mr if r["task"] == t and r["condition"] == c),
                                    sum(1 for r in mr if r["task"] == t and r["condition"] == c)] for c in conds}
    return out


def _pts(x: float) -> str:
    s = f"{x * 100:+.0f}"
    return "0" if s in ("+0", "-0") else s


def markdown(s: dict) -> str:
    pc = lambda x: f"{x * 100:.0f}%"
    md = [f"# Paired test summary ({s['n_runs']} scored runs; baseline: {s['baseline']})", ""]
    for model, m in s["models"].items():
        md += [f"## {model}", "", "| Condition | Passed | Pass rate (95% Wilson) | vs baseline, points (95% bootstrap over tasks) | p (permutation) | Tasks better/worse | Mean cost US$ | Cost per pass US$ | Skill loaded |",
               "|---|---|---|---|---|---|---|---|---|"]
        for c, x in m["conditions"].items():
            p = m["paired"].get(c, {}).get("all") or {}
            vs = f"{_pts(p['diff'])} ({_pts(p['ci'][0])} to {_pts(p['ci'][1])})" if p else "–"
            pp = f"{p['p_perm']:.2f}" if p else "–"
            tb = f"{p['tasks_better']}/{p['tasks_worse']} of {p['tasks']}" if p else "–"
            cpp = f"{x['cost_per_pass']:.4f}" if x["cost_per_pass"] is not None else "n/a"
            md.append(f"| {c} | {x['passed']}/{x['n']} | {pc(x['pass_rate'])} ({pc(x['wilson'][0])}–{pc(x['wilson'][1])}) | {vs} | {pp} | {tb} | "
                      f"{x['cost_mean']:.4f} | {cpp} | {pc(x['skill_loaded_rate'])} |")
        conds = list(m["conditions"])
        md += ["", "| Task | " + " | ".join(conds) + " |", "|---" * (len(conds) + 1) + "|"]
        for t, row in m["per_task"].items():
            md.append(f"| {t} | " + " | ".join(f"{row[c][0]}/{row[c][1]}" for c in conds) + " |")
        md += ["", "Failed checks: " + "; ".join(f"{c}: " + (", ".join(f"{k} {v}" for k, v in x["failed_checks"].items()) or "none")
                                               for c, x in m["conditions"].items()), ""]
    md.append("Read the task-level interval, not the run-level one: repeats of one task are not independent.")
    return "\n".join(md) + "\n"

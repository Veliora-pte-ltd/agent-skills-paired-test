"""Analyse the subscription follow-up (release tasks; Opus 5.5 and Fable 5.1 on Claude Pro) next to the
main experiment's release runs. Writes results/subscription-summary.json and .md."""
from __future__ import annotations

import json
import statistics as st
from collections import Counter, defaultdict

from analyse import RES, load, paired_diff, wilson

SUB = "subscription-rerun.jsonl"


def cell(rs: list[dict], cost_key: str) -> dict:
    n, k = len(rs), sum(r["passed"] for r in rs)
    cost = [r.get(cost_key) or 0.0 for r in rs]
    return {"n": n, "passed": k, "pass_rate": k / n if n else None, "wilson": wilson(k, n),
            "cost_mean": st.mean(cost) if rs else None, "cost_total": sum(cost),
            "cost_per_pass": sum(cost) / k if k else None,
            "wall_median": st.median(r["wall_s"] for r in rs) if rs else None,
            "turns_mean": st.mean(r.get("num_turns") or 0 for r in rs) if rs else None,
            "output_tokens_mean": st.mean(r["usage"]["output"] for r in rs) if rs else None,
            "skill_loaded_rate": sum(bool(r.get("skill_calls")) for r in rs) / n if n else None,
            "failed_checks": dict(Counter(c["name"] for r in rs for c in r["checks"] if not c["ok"]).most_common())}


def per_task(rs):
    d = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rs:
        d[r["task"]][r["condition"]][0] += r["passed"]; d[r["task"]][r["condition"]][1] += 1
    return {t: {c: v for c, v in sorted(x.items())} for t, x in sorted(d.items())}


def main() -> None:
    raw = load(SUB)
    sub = [r for r in raw if "passed" in r]
    aborted = [{k: r.get(k) for k in ("task", "condition", "model", "rep", "aborted", "final_text")} for r in raw if "aborted" in r]
    events = [r for r in raw if "event" in r]
    out = {"subscription": {}, "main_release": {}, "aborted": aborted, "events": events}
    for m in sorted({r["model"] for r in sub}):
        rs = [r for r in sub if r["model"] == m]
        out["subscription"][m] = {
            "conditions": {c: cell([r for r in rs if r["condition"] == c], "cost_estimate_usd") for c in ("none", "compact")},
            "paired_compact": paired_diff(rs, "compact"),
            "per_task": per_task(rs),
            "overage_runs": sum(bool(r.get("used_overage")) for r in rs),
            "api_key_sources": dict(Counter(str(r.get("api_key_source")) for r in rs)),
            "cost_estimate_total": sum(r.get("cost_estimate_usd") or 0 for r in rs),
            "wall_total_s": sum(r["wall_s"] for r in rs),
        }
    main_rel = [r for r in load("main.jsonl") if r.get("family") == "release" and "passed" in r]
    for m in sorted({r["model"] for r in main_rel}):
        rs = [r for r in main_rel if r["model"] == m]
        out["main_release"][m] = {
            "conditions": {c: cell([r for r in rs if r["condition"] == c], "cost_usd") for c in ("none", "compact")},
            "per_task": per_task(rs)}
    (RES / "subscription-summary.json").write_text(json.dumps(out, indent=1, default=float))
    md = ["# Subscription follow-up: release tasks", ""]
    for src, label in (("subscription", "Claude Pro subscription (cost = Claude Code estimate)"),
                       ("main_release", "Main experiment, API (cost = published prices)")):
        md += [f"## {label}", "", "| Model | Condition | Passed | Pass rate (95% Wilson) | Mean cost US$ | Wall median s |", "|---|---|---|---|---|---|"]
        for m, v in out[src].items():
            for c, x in v["conditions"].items():
                if not x["n"]:
                    continue
                lo, hi = x["wilson"]
                md.append(f"| {m} | {c} | {x['passed']}/{x['n']} | {x['pass_rate']*100:.0f}% ({lo*100:.0f}-{hi*100:.0f}%) | "
                          f"{x['cost_mean']:.4f} | {x['wall_median']:.1f} |")
        md.append("")
    for m, v in out["subscription"].items():
        p = v["paired_compact"]
        if p:
            md.append(f"- {m}: compact vs none, mean per-task difference {p['diff']*100:+.0f} points "
                      f"(95% bootstrap {p['ci'][0]*100:+.0f} to {p['ci'][1]*100:+.0f}), tasks better {p['tasks_better']}/{p['tasks']}, "
                      f"p_perm {p['p_perm']:.3f}; cost estimate total ${v['cost_estimate_total']:.2f}")
    md += ["", f"Aborted runs: {len(aborted)}; events: {events}"]
    (RES / "subscription-summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()

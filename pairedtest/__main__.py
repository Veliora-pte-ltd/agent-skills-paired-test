"""Command line.

    python -m pairedtest plan    SUITE --models M [--conditions none compact] [--repeats 5]
    python -m pairedtest oracle  SUITE        reference solutions must pass, untouched repos must fail
    python -m pairedtest run     SUITE --models M --out DIR [--auth api|subscription] [--budget 5] [--cap 1]
    python -m pairedtest report  DIR/runs.jsonl [--baseline none] [--json summary.json]

`plan`, `oracle` and `report` make no model calls.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import pricing
from .report import load, markdown, summarise
from .runner import Config, Runner, make_plan
from .suite import load as load_suite


def oracle(suite) -> int:
    if not hasattr(suite, "solve"):
        print("the suite has no solve(task, workdir); add reference solutions to check the checkers")
        return 1
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for tid, task in suite.TASKS.items():
            base, wd, noop = (Path(tmp, tid, x) for x in ("base", "wd", "noop"))
            for d in (base, wd, noop):
                suite.prepare(task, d, None)
            suite.solve(task, wd)
            res = suite.verify(task, wd, base)
            fails = [c for c in res if not c[1]]
            noop_pass = bool(res) and all(c[1] for c in suite.verify(task, noop, base))
            print(f"{tid:24s} reference {'PASS' if res and not fails else 'FAIL'} ({len(res)} checks)   "
                  f"untouched {'PASS (checker too weak!)' if noop_pass else 'fails, as it should'}")
            for c in fails:
                print("     failed:", c)
            bad += bool(fails) + noop_pass + (not res)
    print("oracle OK" if not bad else f"oracle: {bad} problem(s)")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pairedtest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "oracle", "run"):
        p = sub.add_parser(name)
        p.add_argument("suite", help="directory containing suite.py")
        if name == "oracle":
            continue
        p.add_argument("--models", nargs="+", required=True)
        p.add_argument("--conditions", nargs="+", default=None, help="default: none plus every condition in SKILLS")
        p.add_argument("--tasks", nargs="+", default=None)
        p.add_argument("--repeats", type=int, default=5)
        p.add_argument("--seed", type=int, default=20261008)
        if name == "run":
            p.add_argument("--out", required=True, help="results directory (runs.jsonl, spend.jsonl, transcripts/)")
            p.add_argument("--auth", choices=["api", "subscription"], default="api")
            p.add_argument("--config-dir", help="subscription: Claude Code config dir holding the login")
            p.add_argument("--claude", default="claude", help="path to the claude binary")
            p.add_argument("--budget", type=float, default=5.0, help="api: stop before total spend could pass this (US$)")
            p.add_argument("--cap", type=float, default=1.0, help="per-run --max-budget-usd (US$); 0 = off (subscription only)")
            p.add_argument("--workers", type=int, default=1)
            p.add_argument("--timeout", type=int, default=900)
            p.add_argument("--prices", help="JSON price table to use instead of pricing.py")
            p.add_argument("--path", nargs="*", default=[], help="extra PATH dirs for the agent (node, a venv with your test tools)")
    r = sub.add_parser("report")
    r.add_argument("runs")
    r.add_argument("--baseline", default="none")
    r.add_argument("--json", help="also write the summary as JSON here")
    a = ap.parse_args(argv)

    if a.cmd == "report":
        s = summarise(load(a.runs), a.baseline)
        if a.json:
            Path(a.json).write_text(json.dumps(s, indent=1, default=float))
        print(markdown(s), end="")
        return 0
    suite = load_suite(a.suite)
    if a.cmd == "oracle":
        return oracle(suite)
    conds = a.conditions or ["none", *suite.SKILLS]
    tasks = a.tasks or list(suite.TASKS)
    unknown = [t for t in tasks if t not in suite.TASKS]
    if unknown:
        ap.error(f"unknown tasks: {unknown}")
    plan = make_plan(tasks, conds, a.models, a.repeats, a.seed)
    if a.cmd == "plan":
        print(f"{len(plan)} runs = {len(tasks)} tasks x {len(conds)} conditions ({', '.join(conds)}) x "
              f"{a.repeats} repeats x {len(a.models)} model(s). No model calls made.")
        for p in plan[:10]:
            print("  ", p)
        return 0
    cfg = Config(out=Path(a.out), auth=a.auth, claude=a.claude, config_dir=Path(a.config_dir) if a.config_dir else None,
                 budget=a.budget, cap=a.cap, workers=a.workers, timeout_s=a.timeout,
                 prices=pricing.load(a.prices), path_dirs=a.path)
    res = Runner(suite, cfg).run(plan)
    print(json.dumps(res))
    return 0 if not res["stopped"] else 2


if __name__ == "__main__":
    sys.exit(main())

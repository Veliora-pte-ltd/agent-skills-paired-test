"""Follow-up: release tasks only, on a Claude subscription login instead of an API key.

    python run_sub.py --dry-run          # print the plan, make no model calls
    python run_sub.py                    # run it (sequential, resumable)

Differences from run.py:
- Auth: the child environment never contains ANTHROPIC_API_KEY, SKILL_AB_API_KEY,
  ANTHROPIC_AUTH_TOKEN or CLAUDE_CODE_OAUTH_TOKEN. Claude Code uses the login stored in
  $SKILL_AB_CLAUDE_CONFIG_DIR (set up once with `claude auth login`). A run whose init event reports an
  API-key source is treated as an auth fault and stops the batch.
- Cost: Claude Code's total_cost_usd is stored as an ESTIMATE only (subscription usage is not billed per
  token). Nothing is written to results/spend.jsonl.
- Output: results/subscription-rerun.jsonl and results/transcripts-subscription/. Existing results untouched.
- Runs one at a time, in rep-major blocks so any prefix is balanced across models and conditions.
- Stops cleanly at the first usage-limit, rate-limit, auth or API error: that run is logged with
  "aborted" and no score, and nothing is retried. Re-running the command resumes where it stopped.
- Same tasks, skills, prompts, flags and checker (verify.py) as the main experiment.
- Fable 5.1 is billed from paid usage credits on Claude Pro: before each Fable run, if the cumulative Fable
  estimate plus the largest Fable run so far ($1.50 before any data) would pass --fable-cap ($20), all
  remaining Fable runs are skipped and Opus continues. Fable runs get --max-budget-usd 1.00.
- A run on an included model (Opus) that reports paid extra usage, or any run on an API key, stops everything.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

os.environ.setdefault("SKILL_AB_SCRATCH", "/tmp/skill-ab-sub")
from run import (AGENT_BIN, CLAUDE, NODE_BIN, RESULTS, SCRATCH, TIMEOUT_S, base_copy,  # noqa: E402
                 claude_cmd, parse_stream, skills_for)
from tasks import TASKS, prepare  # noqa: E402
from verify import verify  # noqa: E402

OUT = RESULTS / "subscription-rerun.jsonl"
TRANSCRIPTS = RESULTS / "transcripts-subscription"
MODELS = ["claude-opus-5-5", "claude-fable-5-1"]
FABLE = "claude-fable-5-1"   # not included in Claude Pro: billed from paid usage credits
FABLE_CAP_USD = 20.0         # hard cap on cumulative Claude Code cost ESTIMATE for Fable
FABLE_FIRST_RESERVE = 1.50   # assumed size of a Fable run before any data
CONDITIONS = ["none", "compact"]
RELEASE_TASKS = [t for t in TASKS if TASKS[t].family == "release"]
SECRET_VARS = ("ANTHROPIC_API_KEY", "SKILL_AB_API_KEY",
               "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
# Account-identifying fields Claude Code may put in stream events; dropped before anything is saved.
PRIVATE_KEYS = re.compile(r"(email|account|org|user_?id|subscription)", re.I)

LIMIT = re.compile(r"usage limit|rate.?limit|hit your limit|limit reached|limit will reset|resets? at|quota|"
                   r"too many requests|\b429\b", re.I)
AUTH = re.compile(r"not logged in|/login|auth(entication)?[_ ]?(error|failed)|oauth|invalid (api key|token|bearer)|"
                  r"token (has )?expired|unauthori[sz]ed|forbidden|\b401\b|\b403\b|credit balance", re.I)


def config_dir() -> Path:
    d = os.environ.get("SKILL_AB_CLAUDE_CONFIG_DIR")
    if not d or not Path(d).is_dir():
        sys.exit("Set SKILL_AB_CLAUDE_CONFIG_DIR to the Claude Code config dir that holds the subscription login.")
    return Path(d)


def child_env(rundir: Path) -> dict:
    env = {
        "PATH": "".join(d + ":" for d in (AGENT_BIN, NODE_BIN) if d) + "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(rundir / "home"), "CLAUDE_CONFIG_DIR": str(config_dir()),
        "LANG": "C.UTF-8", "TERM": "dumb",
        "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    for v in SECRET_VARS:
        env.pop(v, None)
    (rundir / "home").mkdir(parents=True, exist_ok=True)
    (rundir / "home" / ".gitconfig").write_text(
        "[user]\n\tname = Sam Developer\n\temail = sam@tillroll.example\n[init]\n\tdefaultBranch = main\n")
    return env


def auth_status() -> dict:
    """Local check only (no model call): `claude auth status --json`."""
    env = child_env(SCRATCH / "auth-check")
    p = subprocess.run([CLAUDE, "auth", "status", "--json"], env=env, capture_output=True, text=True, timeout=60)
    try:
        st = json.loads(p.stdout)
    except json.JSONDecodeError:
        st = {"raw": (p.stdout + p.stderr).strip()[:200]}
    return {k: v for k, v in st.items() if not PRIVATE_KEYS.search(k)} if isinstance(st, dict) else {"raw": str(st)[:200]}


def scrub(obj):
    if isinstance(obj, dict):
        return {k: ("[removed]" if PRIVATE_KEYS.search(k) else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def rate_limit_infos(lines: list[str]) -> list[dict]:
    out = []
    for l in lines:
        try:
            ev = json.loads(l)
        except json.JSONDecodeError:
            continue
        if "rate_limit" in str(ev.get("type", "")):
            out.append(ev.get("rate_limit_info", ev))
    return out


def used_overage(lines: list[str]) -> bool:
    """True if any rate-limit event says the run drew on paid extra usage."""
    for info in rate_limit_infos(lines):
        if info.get("isUsingOverage") is True or str(info.get("overageStatus", "")).lower() in ("using", "active"):
            return True
    return False


def classify(lines: list[str], stderr: str, rc: int) -> str | None:
    """Return 'limit', 'auth' or 'api_error' if the run hit one; None for a normal (pass or fail) run."""
    result, init, events = None, None, []
    for l in lines:
        try:
            ev = json.loads(l)
        except json.JSONDecodeError:
            continue
        t = str(ev.get("type", ""))
        if t == "result":
            result = ev
        elif t == "system" and ev.get("subtype") == "init":
            init = ev
        if "rate_limit" in t:
            events.append(ev)
    src = str((init or {}).get("apiKeySource") or "")
    if "API_KEY" in src.upper() or "apikeyhelper" in src.lower():
        return "auth"  # must never run on an API key
    for ev in events:
        info = ev.get("rate_limit_info", ev)
        if str(info.get("status", "")).lower() in ("rejected", "blocked", "exceeded"):
            return "limit"
    status = (result or {}).get("api_error_status")
    if status == 429:
        return "limit"
    if status in (401, 403):
        return "auth"
    text = " ".join([str((result or {}).get("result") or ""), stderr[-3000:]])
    if stderr == "timeout":
        return None  # the 900 s harness timeout: scored as a failed run, as in the main experiment
    errored = result is None or bool(result.get("is_error")) or status is not None or rc not in (0,)
    if result is not None and result.get("subtype") == "error_max_budget_usd":
        return None  # per-run guard hit: an ordinary failed run, not a reason to stop
    if errored:
        if LIMIT.search(text):
            return "limit"
        if AUTH.search(text):
            return "auth"
        if status is not None or result is None:
            return "api_error"
    return None


def prior_records() -> list[dict]:
    if not OUT.exists():
        return []
    return [r for r in map(json.loads, OUT.read_text().splitlines()) if "run_id" in r]


def done_keys() -> set:
    if not OUT.exists():
        return set()
    keys = set()
    for r in prior_records():
        if "passed" in r:
            keys.add((r["task"], r["condition"], r["model"], r["rep"]))
    return keys


def run_one(task_id: str, cond: str, model: str, rep: int, cap: float) -> dict:
    task = TASKS[task_id]
    run_id = f"sub-{task_id}-{cond}-{model}-r{rep}-{uuid.uuid4().hex[:6]}"
    rundir = SCRATCH / "runs" / run_id
    wd = rundir / "repo"
    rec = {"run_id": run_id, "phase": "subscription-rerun", "task": task_id, "family": task.family,
           "condition": cond, "model": model, "rep": rep, "started": time.time(), "billing": "subscription"}
    try:
        prepare(task, wd, skills_for(cond, model))
        cmd = claude_cmd(task.prompt, model, cap, [])
        if cap <= 0:
            i = cmd.index("--max-budget-usd"); del cmd[i:i + 2]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=wd, env=child_env(rundir), capture_output=True, text=True, timeout=TIMEOUT_S)
            out, err, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err, rc = "timeout", -9
        wall = time.time() - t0
        lines = []
        for l in out.splitlines():
            try:
                lines.append(json.dumps(scrub(json.loads(l))))
            except json.JSONDecodeError:
                lines.append(l)
        TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
        with gzip.open(TRANSCRIPTS / f"{run_id}.jsonl.gz", "wt") as fh:
            fh.write("\n".join(lines) + "\n")
        info = parse_stream(lines)
        stop = classify(lines, err, rc)
        init = next((json.loads(l) for l in lines if '"subtype": "init"' in l or '"subtype":"init"' in l), {})
        rec.update({k: v for k, v in info.items() if k not in ("cost_usd", "cost_by_model", "cli_cost_usd")})
        rec["rate_limit_events"] = [{k: v for k, v in i.items() if k != "type"} for i in rate_limit_infos(lines)][-3:]
        rec["used_overage"] = used_overage(lines)
        if stop is None and model != FABLE and rec["used_overage"]:
            stop = "overage_on_included_model"  # Opus must stay inside the plan: stop everything
        rec.update({"cost_estimate_usd": info["cli_cost_usd"], "cost_estimate_note":
                    ("Claude Code total_cost_usd (estimate); Fable is billed from Pro usage credits" if model == FABLE
                     else "Claude Code total_cost_usd (estimate); inside the Claude Pro plan, not billed per token"),
                    "api_key_source": init.get("apiKeySource"), "wall_s": round(wall, 2), "exit_code": rc})
        if stop:
            rec.update({"aborted": stop, "stderr_tail": err[-500:]})
            return rec
        checks = verify(task, wd, base_copy(task))
        rec.update({"checks": [{"name": n, "ok": ok, "detail": str(d)[:300]} for n, ok, d in checks],
                    "score": sum(ok for _, ok, _ in checks) / max(1, len(checks)),
                    "passed": bool(checks) and all(ok for _, ok, _ in checks)})
        return rec
    finally:
        shutil.rmtree(rundir, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=4)
    ap.add_argument("--models", nargs="+", default=MODELS)
    ap.add_argument("--conditions", nargs="+", default=CONDITIONS)
    ap.add_argument("--cap", type=float, default=1.50,
                    help="per-run guard passed to --max-budget-usd (estimated US$); 0 disables it")
    ap.add_argument("--fable-cap", type=float, default=FABLE_CAP_USD,
                    help="stop Fable once its cumulative estimated cost would pass this")
    ap.add_argument("--fable-run-cap", type=float, default=1.00, help="per-run --max-budget-usd for Fable")
    ap.add_argument("--seed", type=int, default=20261009)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for v in SECRET_VARS:  # belt and braces: nothing below may see a key
        os.environ.pop(v, None)
    plan = []
    rng = random.Random(a.seed)
    for r in range(a.repeats):  # rep-major blocks: every prefix stays balanced
        block = [(t, c, m, r) for m in a.models for t in RELEASE_TASKS for c in a.conditions]
        rng.shuffle(block)
        plan += block
    have = done_keys()
    todo = [p for p in plan if p not in have]
    print(f"plan {len(plan)} runs ({len(RELEASE_TASKS)} release tasks x {len(a.conditions)} conditions x "
          f"{a.repeats} repeats x {len(a.models)} models); already done {len(plan) - len(todo)}; to do {len(todo)}")
    if a.dry_run:
        for p in todo[:12]:
            print("  ", p)
        return
    RESULTS.mkdir(exist_ok=True)
    st = auth_status()
    print("auth status:", st)
    if not st.get("loggedIn"):
        sys.exit("Not logged in for SKILL_AB_CLAUDE_CONFIG_DIR. Run `claude auth login` first. No runs started.")
    if any(w in str(st.get("authMethod", "")).lower() for w in ("api", "console", "key")):
        sys.exit(f"Login is not a Claude subscription ({st.get('authMethod')}). No runs started.")
    shutil.rmtree(SCRATCH / "base", ignore_errors=True)  # never verify against a stale starting state
    fable = [x for x in prior_records() if x.get("model") == FABLE]
    fable_cum = sum(x.get("cost_estimate_usd") or 0 for x in fable)
    fable_max = max([x.get("cost_estimate_usd") or 0 for x in fable], default=0)
    fable_stopped = False
    print(f"Fable cumulative estimate so far ${fable_cum:.4f} of ${a.fable_cap:.2f}", flush=True)
    for i, (t, c, m, r) in enumerate(todo, 1):
        if m == FABLE:
            reserve = fable_max if fable_max > 0 else FABLE_FIRST_RESERVE
            if not fable_stopped and fable_cum + reserve > a.fable_cap:
                fable_stopped = True
                print(f"FABLE CAP: cumulative ${fable_cum:.4f} + reserve ${reserve:.4f} > ${a.fable_cap:.2f}; "
                      f"skipping all remaining Fable runs, continuing with Opus only", flush=True)
                with open(OUT, "a") as fh:
                    fh.write(json.dumps({"event": "fable_cap_stop", "t": time.time(), "fable_cum_estimate": fable_cum,
                                         "reserve": reserve, "cap": a.fable_cap}) + "\n")
            if fable_stopped:
                continue
        rec = run_one(t, c, m, r, a.fable_run_cap if m == FABLE else a.cap)
        if m == FABLE:
            est = rec.get("cost_estimate_usd") or 0
            fable_cum += est
            fable_max = max(fable_max, est)
            rec["fable_cum_estimate"] = round(fable_cum, 6)
            if not est and (rec.get("usage") or {}).get("output", 0) > 0 and not fable_stopped:
                fable_stopped = True  # fail safe: without a cost estimate the cap cannot be enforced
                print("FABLE CAP: run reported no cost estimate; skipping all remaining Fable runs", flush=True)
                with open(OUT, "a") as fh:
                    fh.write(json.dumps({"event": "fable_cap_stop", "reason": "no_cost_estimate", "t": time.time()}) + "\n")
        with open(OUT, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        if "aborted" in rec:
            print(f"STOPPED at run {i}/{len(todo)} ({t} {c} {m} r{r}): {rec['aborted']}. "
                  f"Progress saved in {OUT.name}; re-run the same command to resume later.", flush=True)
            sys.exit(2)
        print(f"[{i}/{len(todo)}] {t:16s} {c:8s} {m:17s} r{r} pass={rec.get('passed')} "
              f"est=${rec.get('cost_estimate_usd') or 0:.4f} {rec.get('wall_s')}s "
              f"skills={len(rec.get('skill_calls') or [])} src={rec.get('api_key_source')} "
              f"overage={rec.get('used_overage')}"
              + (f" FABLE_CUM=${fable_cum:.4f}" if m == FABLE else ""), flush=True)
    print("done:", len(done_keys()), "scored runs in", OUT.name)


if __name__ == "__main__":
    main()

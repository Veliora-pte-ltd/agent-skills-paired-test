"""Run the skill A/B experiment with Claude Code in headless mode.

    python run.py smoke                 # one cheap run per family, to validate the harness
    python run.py selfgen --model M     # let the agent write its own skills (condition "selfgen")
    python run.py main --model M --repeats R [--conditions ...] [--tasks ...]
    python run.py trigger --model M

The API key is read from ANTHROPIC_API_KEY (or SKILL_AB_API_KEY) and is only
ever passed to the child process environment. Every run's cost is computed from
the token usage the API returns, times the published prices in pricing.py, and
appended to results/spend.jsonl. Before each run the harness checks that the
total spent, plus the in-flight runs' caps, stays under --budget (default $27).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pricing import call_cost
from tasks import TASKS, Task, prepare
from verify import verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = ROOT / "results"
SKILLS = ROOT / "skills"
SCRATCH = Path(os.environ.get("SKILL_AB_SCRATCH", "/tmp/skill-ab"))
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
NODE_BIN = os.environ.get("NODE_BIN_DIR", "")  # optional dir with node >= 22 and claude
AGENT_BIN = os.environ.get("AGENT_VENV_BIN", "")  # optional venv bin dir with python3 + pytest for the agent
TIMEOUT_S = 900

LOCK = threading.Lock()
IN_FLIGHT: dict[str, float] = {}


def api_key() -> str:
    key = os.environ.get("SKILL_AB_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("Set ANTHROPIC_API_KEY (or SKILL_AB_API_KEY) in the environment.")
    return key


# ------------------------------------------------------------------ spend
def spent() -> float:
    f = RESULTS / "spend.jsonl"
    if not f.exists():
        return 0.0
    return sum(json.loads(l)["cost_usd"] for l in f.read_text().splitlines() if l.strip())


def reserve(run_id: str, cap: float, budget: float) -> bool:
    with LOCK:
        if spent() + sum(IN_FLIGHT.values()) + cap > budget:
            return False
        IN_FLIGHT[run_id] = cap
        return True


def settle(run_id: str, phase: str, cost: float, cli_cost: float | None) -> None:
    with LOCK:
        IN_FLIGHT.pop(run_id, None)
        with open(RESULTS / "spend.jsonl", "a") as fh:
            fh.write(json.dumps({"run_id": run_id, "phase": phase, "cost_usd": round(cost, 6),
                                 "cli_reported_usd": cli_cost, "t": time.time()}) + "\n")


# ------------------------------------------------------------ transcript parse
def parse_stream(lines: list[str]) -> dict:
    msgs, tools, result, init = {}, [], None, None
    for l in lines:
        try:
            ev = json.loads(l)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            init = ev
        elif t == "assistant":
            m = ev["message"]
            if ev.get("parent_tool_use_id") is None:
                msgs[m["id"]] = m  # the same id is repeated per content block; keep the last
            for b in m.get("content", []):
                if b.get("type") == "tool_use":
                    tools.append({"name": b["name"], "input": b.get("input", {})})
        elif t == "result":
            result = ev
    # Input-side usage per API call is reliable in the stream; output_tokens there is a partial
    # count, so totals come from the result event's modelUsage. Cost = tokens x published prices.
    max_prompt = 0
    for m in msgs.values():
        u = m.get("usage", {})
        max_prompt = max(max_prompt, u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                         + u.get("cache_read_input_tokens", 0))
    usage = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    cost, cost_by_model = 0.0, {}
    for model, mu in ((result or {}).get("modelUsage") or {}).items():
        i, cw, cr, o = (mu.get("inputTokens", 0), mu.get("cacheCreationInputTokens", 0),
                        mu.get("cacheReadInputTokens", 0), mu.get("outputTokens", 0))
        usage["input"] += i; usage["cache_write"] += cw; usage["cache_read"] += cr; usage["output"] += o
        try:
            c = call_cost(model, i, cw, cr, o, long_prompt=max_prompt > 100_000)
        except KeyError:
            c = float(mu.get("costUSD", 0.0))
        cost_by_model[model] = c
        cost += c
    skill_calls = []
    for tl in tools:
        inp = json.dumps(tl["input"])
        if tl["name"] == "Skill":
            skill_calls.append(tl["input"].get("skill") or tl["input"].get("command") or inp[:80])
        elif "SKILL.md" in inp and tl["name"] in ("Read", "Bash", "Grep", "Glob"):
            skill_calls.append("read:" + inp[:120])
    return {
        "api_calls": len(msgs), "usage": usage, "cost_usd": cost, "cost_by_model": cost_by_model,
        "max_prompt_tokens": max_prompt,
        "cli_cost_usd": (result or {}).get("total_cost_usd"), "num_turns": (result or {}).get("num_turns"),
        "duration_ms": (result or {}).get("duration_ms"), "is_error": (result or {}).get("is_error"),
        "result_subtype": (result or {}).get("subtype"), "tool_calls": len(tools),
        "tool_names": [t["name"] for t in tools], "skill_calls": skill_calls,
        "skills_listed": [s for s in (init or {}).get("skills", [])] if init else None,
        "claude_code_version": (init or {}).get("claude_code_version"),
        "final_text": ((result or {}).get("result") or "")[:2000],
    }


# ------------------------------------------------------------------ one run
def claude_cmd(prompt: str, model: str, cap: float, extra: list[str]) -> list[str]:
    return [CLAUDE, "-p", prompt, "--output-format", "stream-json", "--verbose", "--model", model,
            "--permission-mode", "bypassPermissions", "--max-budget-usd", f"{cap:.2f}",
            "--no-session-persistence", "--exclude-dynamic-system-prompt-sections",
            "--setting-sources", "project", "--disallowedTools", "WebFetch", "WebSearch", *extra]


def child_env(rundir: Path) -> dict:
    env = {
        "PATH": "".join(d + ":" for d in (AGENT_BIN, NODE_BIN) if d) + "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(rundir / "home"), "CLAUDE_CONFIG_DIR": str(rundir / "home" / ".claude"),
        "ANTHROPIC_API_KEY": api_key(), "LANG": "C.UTF-8", "TERM": "dumb",
        "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    (rundir / "home" / ".claude").mkdir(parents=True, exist_ok=True)
    # A developer machine has a git identity; without one the agent cannot commit and stops to ask.
    (rundir / "home" / ".gitconfig").write_text(
        "[user]\n\tname = Sam Developer\n\temail = sam@tillroll.example\n[init]\n\tdefaultBranch = main\n")
    return env


def exec_claude(rundir: Path, cwd: Path, cmd: list[str]) -> tuple[list[str], float, int]:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=child_env(rundir), capture_output=True, text=True, timeout=TIMEOUT_S)
        out, rc = p.stdout, p.returncode
        err = p.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err, rc = "timeout", -9
    wall = time.time() - t0
    key = api_key()
    if key in out or key in err:  # never store the key, even if a tool printed it
        out, err = out.replace(key, "[REDACTED]"), err.replace(key, "[REDACTED]")
    (rundir / "stderr.txt").write_text(err[-5000:])
    return out.splitlines(), wall, rc


def save_transcript(run_id: str, lines: list[str]) -> None:
    d = RESULTS / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / f"{run_id}.jsonl.gz", "wt") as fh:
        fh.write("\n".join(lines) + "\n")


def skills_for(condition: str, model: str) -> Path | None:
    if condition == "none":
        return None
    if condition == "selfgen":
        p = SKILLS / "self-generated" / model
        if not p.exists():
            raise FileNotFoundError(f"run `python run.py selfgen --model {model}` first")
        return p
    return SKILLS / condition


def base_copy(task: Task) -> Path:
    b = SCRATCH / "base" / task.id
    with LOCK:
        if not b.exists():
            prepare(task, b)
    return b


def run_task(phase: str, task: Task, condition: str, model: str, rep: int, cap: float, budget: float) -> dict | None:
    run_id = f"{phase}-{task.id}-{condition}-{model}-r{rep}-{uuid.uuid4().hex[:6]}"
    if not reserve(run_id, cap, budget):
        return None
    rundir = SCRATCH / "runs" / run_id
    wd = rundir / "repo"
    rec = {"run_id": run_id, "phase": phase, "task": task.id, "family": task.family,
           "condition": condition, "model": model, "rep": rep, "started": time.time()}
    cost, cli = 0.0, None
    try:
        prepare(task, wd, skills_for(condition, model))
        lines, wall, rc = exec_claude(rundir, wd, claude_cmd(task.prompt, model, cap, []))
        save_transcript(run_id, lines)
        info = parse_stream(lines)
        cost, cli = info["cost_usd"], info["cli_cost_usd"]
        checks = verify(task, wd, base_copy(task))
        rec.update(info)
        rec.update({"wall_s": round(wall, 2), "exit_code": rc,
                    "checks": [{"name": n, "ok": ok, "detail": str(d)[:300]} for n, ok, d in checks],
                    "score": sum(ok for _, ok, _ in checks) / max(1, len(checks)),
                    "passed": bool(checks) and all(ok for _, ok, _ in checks)})
    finally:
        settle(run_id, phase, max(cost, cli or 0.0), cli)
        shutil.rmtree(rundir, ignore_errors=True)
    with LOCK:
        with open(RESULTS / f"{phase}.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    return rec


# ------------------------------------------------------------------ phases
SELFGEN_PROMPTS = {
    "db-migrations": (
        "Study this repository and write an Agent Skill that teaches a coding agent how to add a database "
        "migration that follows this project's conventions. Use the Agent Skills format: a file "
        ".claude/skills/db-migrations/SKILL.md with YAML front matter containing `name: db-migrations` and a "
        "`description` saying what the skill does and when to use it, followed by Markdown instructions. "
        "Base it only on what you can find in the repository. Do not change any other file."),
    "release": (
        "Study this repository and write an Agent Skill that teaches a coding agent how to cut a release of "
        "this project following its conventions. Use the Agent Skills format: a file "
        ".claude/skills/release/SKILL.md with YAML front matter containing `name: release` and a "
        "`description` saying what the skill does and when to use it, followed by Markdown instructions. "
        "Base it only on what you can find in the repository. Do not change any other file."),
}


def phase_selfgen(model: str, cap: float, budget: float) -> None:
    out_dir = SKILLS / "self-generated" / model
    for name, prompt in SELFGEN_PROMPTS.items():
        run_id = f"selfgen-{name}-{model}-{uuid.uuid4().hex[:6]}"
        if not reserve(run_id, cap, budget):
            sys.exit("budget reached")
        rundir = SCRATCH / "runs" / run_id
        wd = rundir / "repo"
        cost, cli = 0.0, None
        try:
            prepare(TASKS["rel-02-minor"], wd)  # fixture plus some unreleased history
            lines, wall, rc = exec_claude(rundir, wd, claude_cmd(prompt, model, cap, []))
            save_transcript(run_id, lines)
            info = parse_stream(lines)
            cost, cli = info["cost_usd"], info["cli_cost_usd"]
            src = wd / ".claude" / "skills" / name / "SKILL.md"
            ok = src.exists()
            if ok:
                (out_dir / name).mkdir(parents=True, exist_ok=True)
                shutil.copy(src, out_dir / name / "SKILL.md")
            rec = {"run_id": run_id, "skill": name, "model": model, "written": ok, "wall_s": round(wall, 2), **info}
            with open(RESULTS / "selfgen.jsonl", "a") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(f"{name}: written={ok} cost=${cost:.4f} cli=${cli}")
        finally:
            settle(run_id, "selfgen", max(cost, cli or 0.0), cli)
            shutil.rmtree(rundir, ignore_errors=True)


def phase_runs(phase: str, plan: list[tuple], cap: float, budget: float, workers: int) -> None:
    done = 0
    stop = threading.Event()

    def work(item):
        nonlocal done
        if stop.is_set():
            return
        tid, cond, model, rep = item
        rec = run_task(phase, TASKS[tid], cond, model, rep, cap, budget)
        if rec is None:
            stop.set()
            print("BUDGET STOP before", item, flush=True)
            return
        with LOCK:
            done += 1
            print(f"[{done}/{len(plan)}] {tid:22s} {cond:13s} {model} r{rep} pass={rec.get('passed')} "
                  f"score={rec.get('score', 0):.2f} ${rec.get('cost_usd', 0):.4f} {rec.get('wall_s')}s "
                  f"skills={len(rec.get('skill_calls') or [])} total=${spent():.3f}", flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, plan))


TRIGGER_FILE = ROOT / "trigger_prompts.json"


def phase_trigger(model: str, cap: float, budget: float, workers: int, max_turns: int) -> None:
    prompts = json.loads(TRIGGER_FILE.read_text())
    items = [(p, kind) for kind in ("should_trigger", "should_not_trigger") for p in prompts[kind]]
    random.Random(7).shuffle(items)
    stop = threading.Event()

    def work(item):
        if stop.is_set():
            return
        prompt, kind = item
        run_id = f"trigger-{model}-{uuid.uuid4().hex[:8]}"
        if not reserve(run_id, cap, budget):
            stop.set()
            return
        rundir = SCRATCH / "runs" / run_id
        wd = rundir / "repo"
        cost, cli = 0.0, None
        try:
            prepare(TASKS["rel-02-minor"], wd, SKILLS / "compact")
            # read-only tools: the trigger test only observes whether a skill is loaded
            extra = ["--max-turns", str(max_turns), "--tools", "Skill", "Read", "Glob", "Grep"]
            lines, wall, rc = exec_claude(rundir, wd, claude_cmd(prompt, model, cap, extra))
            save_transcript(run_id, lines)
            info = parse_stream(lines)
            cost, cli = info["cost_usd"], info["cli_cost_usd"]
            rec = {"run_id": run_id, "model": model, "prompt": prompt, "kind": kind, "wall_s": round(wall, 2),
                   "triggered": bool(info["skill_calls"]), **info}
            with LOCK:
                with open(RESULTS / "trigger.jsonl", "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
                print(f"{kind:18s} trig={rec['triggered']} {info['skill_calls']} ${cost:.4f} :: {prompt[:60]}", flush=True)
        finally:
            settle(run_id, "trigger", max(cost, cli or 0.0), cli)
            shutil.rmtree(rundir, ignore_errors=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, items))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["smoke", "pilot", "selfgen", "main", "trigger"])
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--conditions", nargs="+", default=["none", "compact", "comprehensive", "selfgen"])
    ap.add_argument("--tasks", nargs="+", default=list(TASKS))
    ap.add_argument("--cap", type=float, default=1.0, help="per-run cap in US$ (passed to --max-budget-usd)")
    ap.add_argument("--budget", type=float, default=27.0, help="stop before total spend would exceed this")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-turns", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261008)
    a = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)
    api_key()
    shutil.rmtree(SCRATCH / "base", ignore_errors=True)  # never verify against a stale starting state
    print(f"spent so far: ${spent():.4f} of ${a.budget:.2f}")
    if a.phase == "smoke":
        plan = [("mig-03-refunds", "none", a.model, 0), ("rel-02-minor", "compact", a.model, 0)]
        phase_runs("smoke", plan, a.cap, a.budget, 2)
    elif a.phase == "selfgen":
        phase_selfgen(a.model, a.cap, a.budget)
    elif a.phase in ("main", "pilot"):
        plan = [(t, c, a.model, r) for r in range(a.repeats) for t in a.tasks for c in a.conditions]
        random.Random(a.seed).shuffle(plan)
        phase_runs(a.phase, plan, a.cap, a.budget, a.workers)
    elif a.phase == "trigger":
        phase_trigger(a.model, a.cap, a.budget, a.workers, a.max_turns)
    print(f"total spent: ${spent():.4f}")


if __name__ == "__main__":
    main()

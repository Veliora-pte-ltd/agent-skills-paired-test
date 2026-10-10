"""Run Claude Code headless on every (task, condition, model, repeat) in a plan and score each run.

Isolation, as in the published experiment: every run gets a fresh copy of the task's repository,
a throwaway HOME with a placeholder git identity, `--setting-sources project` (so nothing from your
own Claude Code settings, skills or memory is used), web tools disabled and permissions bypassed
inside the copy. The copy is deleted after scoring; the transcript is kept, gzipped.

Two ways to pay:
- auth="api": ANTHROPIC_API_KEY is passed to the child process only and never written to disk.
  Cost is tokens x list price (pricing.py) and every run is appended to spend.jsonl. Before each
  run the ledger total plus the caps of runs in flight must stay under `budget`, or the batch stops.
- auth="subscription": every API-key variable is removed from the child environment and Claude
  Code uses the login stored in `config_dir` (set up once with `claude auth login`). Costs are
  Claude Code's estimates only. The batch stops at the first usage-limit, auth or API error.

Batches are resumable: re-running the same command skips runs already scored in runs.jsonl.
"""
from __future__ import annotations

import gzip
import json
import os
import random
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import pricing
from .stream import classify, parse_stream, scrub
from .suite import skills_for

KEY_VARS = ("ANTHROPIC_API_KEY", "SKILL_AB_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


@dataclass
class Config:
    out: Path
    auth: str = "api"                 # "api" or "subscription"
    claude: str = "claude"
    config_dir: Path | None = None    # subscription: Claude Code config dir holding the login
    budget: float = 10.0              # api: stop before the ledger could pass this (US$)
    cap: float = 1.0                  # per-run --max-budget-usd; 0 disables (subscription only)
    workers: int = 1
    timeout_s: int = 900
    scratch: Path = Path(os.environ.get("PAIREDTEST_SCRATCH", "/tmp/pairedtest"))
    prices: dict = field(default_factory=lambda: dict(pricing.PRICES))
    path_dirs: list = field(default_factory=list)
    extra_args: list = field(default_factory=list)


def make_plan(task_ids, conditions, models, repeats: int, seed: int = 20261008) -> list[tuple]:
    """Repeat-major blocks, each shuffled, so any prefix of the plan stays balanced across tasks,
    conditions and models (a batch stopped by a budget or a usage limit is still comparable)."""
    rng = random.Random(seed)
    plan = []
    for r in range(repeats):
        block = [(t, c, m, r) for m in models for t in task_ids for c in conditions]
        rng.shuffle(block)
        plan += block
    return plan


def api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("SKILL_AB_API_KEY")
    if not key:
        raise SystemExit("Set ANTHROPIC_API_KEY in the environment (or use --auth subscription).")
    return key


def claude_cmd(cfg: Config, prompt: str, model: str, cap: float, extra=()) -> list[str]:
    cmd = [cfg.claude, "-p", prompt, "--output-format", "stream-json", "--verbose", "--model", model,
           "--permission-mode", "bypassPermissions", "--no-session-persistence",
           "--exclude-dynamic-system-prompt-sections", "--setting-sources", "project",
           "--disallowedTools", "WebFetch", "WebSearch", *cfg.extra_args, *extra]
    if cap > 0:
        cmd[cmd.index("--no-session-persistence"):cmd.index("--no-session-persistence")] = ["--max-budget-usd", f"{cap:.2f}"]
    return cmd


def child_env(cfg: Config, rundir: Path, suite=None) -> dict:
    extra_path = list(cfg.path_dirs) + list(getattr(suite, "AGENT_PATH", []) or [])
    home = rundir / "home"
    env = {
        "PATH": "".join(d + ":" for d in extra_path if d) + "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home), "LANG": "C.UTF-8", "TERM": "dumb",
        "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    if cfg.auth == "api":
        env["ANTHROPIC_API_KEY"] = api_key()
        env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
    elif cfg.auth == "subscription":
        if not cfg.config_dir or not Path(cfg.config_dir).is_dir():
            raise SystemExit("--auth subscription needs --config-dir: a Claude Code config dir with a login "
                             "(CLAUDE_CONFIG_DIR=<dir> claude auth login).")
        env["CLAUDE_CONFIG_DIR"] = str(cfg.config_dir)
        for v in KEY_VARS:
            env.pop(v, None)
    else:
        raise SystemExit(f"unknown auth mode {cfg.auth!r}")
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    # A developer machine has a git identity; without one the agent cannot commit and stops to ask.
    name, email = getattr(suite, "GIT_IDENTITY", ("Sam Developer", "sam@example.com"))
    (home / ".gitconfig").write_text(f"[user]\n\tname = {name}\n\temail = {email}\n[init]\n\tdefaultBranch = main\n")
    return env


class Ledger:
    """spend.jsonl plus an in-flight reservation, so parallel runs cannot overshoot the budget."""

    def __init__(self, path: Path, budget: float, enabled: bool = True):
        self.path, self.budget, self.enabled = path, budget, enabled
        self.lock = threading.Lock()
        self.in_flight: dict[str, float] = {}

    def spent(self) -> float:
        if not self.path.exists():
            return 0.0
        return sum(json.loads(l)["cost_usd"] for l in self.path.read_text().splitlines() if l.strip())

    def reserve(self, run_id: str, cap: float) -> bool:
        if not self.enabled:
            return True
        with self.lock:
            if self.spent() + sum(self.in_flight.values()) + cap > self.budget:
                return False
            self.in_flight[run_id] = cap
            return True

    def settle(self, run_id: str, cost: float, cli_cost: float | None) -> None:
        if not self.enabled:
            return
        with self.lock:
            self.in_flight.pop(run_id, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as fh:
                fh.write(json.dumps({"run_id": run_id, "cost_usd": round(cost, 6),
                                     "cli_reported_usd": cli_cost, "t": time.time()}) + "\n")


def _exec(cfg: Config, cmd: list[str], cwd: Path, env: dict) -> tuple[list[str], str, float, int]:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=cfg.timeout_s)
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err, rc = "timeout", -9
    wall = time.time() - t0
    key = env.get("ANTHROPIC_API_KEY")
    if key:  # never store the key, even if a tool printed it
        out, err = out.replace(key, "[REDACTED]"), err.replace(key, "[REDACTED]")
    lines = []
    for line in out.splitlines():
        try:
            lines.append(json.dumps(scrub(json.loads(line))))
        except json.JSONDecodeError:
            lines.append(line)
    return lines, err, wall, rc


class Runner:
    def __init__(self, suite, cfg: Config):
        self.suite, self.cfg = suite, cfg
        self.cfg.out = Path(cfg.out)
        self.records = self.cfg.out / "runs.jsonl"
        self.ledger = Ledger(self.cfg.out / "spend.jsonl", cfg.budget, enabled=(cfg.auth == "api"))
        self.lock = threading.Lock()
        if cfg.auth == "api" and cfg.cap <= 0:
            raise SystemExit("--auth api needs a per-run --cap above 0, so the budget guard can work.")

    # starting state the checker compares against: rebuilt once per invocation, never reused across runs
    def base_copy(self, task) -> Path:
        b = self.cfg.scratch / "base" / task.id
        with self.lock:
            if not b.exists():
                self.suite.prepare(task, b, None)
        return b

    def done_keys(self) -> set:
        if not self.records.exists():
            return set()
        return {(r["task"], r["condition"], r["model"], r["rep"])
                for r in map(json.loads, filter(str.strip, self.records.read_text().splitlines())) if "passed" in r}

    def run_one(self, task_id: str, cond: str, model: str, rep: int) -> dict | None:
        task = self.suite.TASKS[task_id]
        run_id = f"{task_id}-{cond}-{model}-r{rep}-{uuid.uuid4().hex[:6]}"
        if not self.ledger.reserve(run_id, self.cfg.cap):
            return None
        rundir = self.cfg.scratch / "runs" / run_id
        wd = rundir / "repo"
        rec = {"run_id": run_id, "task": task_id, "family": task.family, "condition": cond, "model": model,
               "rep": rep, "auth": self.cfg.auth, "started": time.time()}
        cost, cli = 0.0, None
        try:
            self.suite.prepare(task, wd, skills_for(self.suite, cond, model))
            env = child_env(self.cfg, rundir, self.suite)
            lines, err, wall, rc = _exec(self.cfg, claude_cmd(self.cfg, task.prompt, model, self.cfg.cap), wd, env)
            tdir = self.cfg.out / "transcripts"
            tdir.mkdir(parents=True, exist_ok=True)
            with open(tdir / f"{run_id}.jsonl.gz", "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as g:
                g.write(("\n".join(lines) + "\n").encode())
            info = parse_stream(lines, self.cfg.prices)
            cost, cli = info["cost_usd"], info["cli_cost_usd"]
            if self.cfg.auth == "subscription":
                info["cost_source"] = "cli_estimate"
                info["cost_usd"] = cost = float(cli or 0.0)
            rec.update(info)
            rec.update({"wall_s": round(wall, 2), "exit_code": rc})
            stop = classify(lines, err, rc, self.cfg.auth)
            if stop:
                rec.update({"aborted": stop, "stderr_tail": err[-500:]})
                return rec
            checks = self.suite.verify(task, wd, self.base_copy(task))
            rec.update({"checks": [{"name": n, "ok": bool(ok), "detail": str(d)[:300]} for n, ok, d in checks],
                        "score": sum(bool(ok) for _, ok, _ in checks) / max(1, len(checks)),
                        "passed": bool(checks) and all(ok for _, ok, _ in checks)})
            return rec
        finally:
            self.ledger.settle(run_id, max(cost, cli or 0.0), cli)
            shutil.rmtree(rundir, ignore_errors=True)

    def run(self, plan: list[tuple], log=print) -> dict:
        self.cfg.out.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.cfg.scratch / "base", ignore_errors=True)  # never verify against a stale start
        have = self.done_keys()
        todo = [p for p in plan if p not in have]
        log(f"plan {len(plan)} runs; already scored {len(plan) - len(todo)}; to do {len(todo)}")
        stop = threading.Event()
        state = {"done": 0, "stopped": None}

        def work(item):
            if stop.is_set():
                return
            rec = self.run_one(*item)
            with self.lock:
                if rec is None:
                    stop.set(); state["stopped"] = "budget"
                    log(f"BUDGET STOP before {item}: ledger ${self.ledger.spent():.2f} of ${self.cfg.budget:.2f}")
                    return
                with open(self.records, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
                if "aborted" in rec:
                    stop.set(); state["stopped"] = rec["aborted"]
                    log(f"STOPPED at {item}: {rec['aborted']}. Re-run the same command to resume.")
                    return
                state["done"] += 1
                log(f"[{state['done']}/{len(todo)}] {item[0]} {item[1]} {item[2]} r{item[3]} "
                    f"pass={rec.get('passed')} ${rec.get('cost_usd', 0):.4f} {rec.get('wall_s')}s "
                    f"skills={rec.get('skill_calls')}")

        if self.cfg.workers <= 1:
            for item in todo:
                work(item)
        else:
            with ThreadPoolExecutor(self.cfg.workers) as ex:
                list(ex.map(work, todo))
        return {"planned": len(plan), "ran": state["done"], "stopped": state["stopped"],
                "spent": self.ledger.spent() if self.ledger.enabled else None}

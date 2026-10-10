"""The published experiment (tillroll, 12 tasks) as a pairedtest suite, so the reusable runner
can run it:  python -m pairedtest oracle skill_ab
             python -m pairedtest run skill_ab --models claude-sonnet-5-5 --out results-mine ...

The tasks, fixture, skills and checker are the ones used for the write-up (tasks.py, verify.py).
"""
from __future__ import annotations

import os
from pathlib import Path

from oracle import solve_migration, solve_release
from tasks import TASKS, prepare  # noqa: F401  (part of the suite interface)
from verify import verify  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
SKILLS = {"compact": ROOT / "skills" / "compact", "comprehensive": ROOT / "skills" / "comprehensive",
          "selfgen": ROOT / "skills" / "self-generated"}
GIT_IDENTITY = ("Sam Developer", "sam@tillroll.example")
AGENT_PATH = [os.environ.get("AGENT_VENV_BIN", "")]  # python3 + pytest for the agent (requirements.txt)


def skills_dir(condition: str, model: str) -> Path:
    if condition == "selfgen":  # each model gets the skills it wrote itself (run.py selfgen)
        p = SKILLS["selfgen"] / model
        if not p.exists():
            raise SystemExit(f"no self-written skills for {model}: run `python run.py selfgen --model {model}` first")
        return p
    return SKILLS[condition]


def solve(task, workdir: Path) -> None:
    (solve_migration if task.family == "migration" else solve_release)(task, workdir)

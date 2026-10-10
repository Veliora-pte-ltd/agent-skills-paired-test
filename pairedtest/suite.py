"""Load a test suite: a directory with a `suite.py` that describes your tasks.

A suite module must define:

    TASKS: dict[str, task]   each task has .id, .family (any label) and .prompt (what a developer would type)
    SKILLS: dict[str, Path]  condition name -> a directory of skills (one sub-directory per skill, each
                             with a SKILL.md). "none" is always available and installs nothing.
    prepare(task, workdir: Path, skills_dir: Path | None) -> None
                             build the task's starting repository in `workdir` (which does not exist yet)
                             and, if skills_dir is given, install those skills (for Claude Code: copy them
                             to workdir/.claude/skills and commit).
    verify(task, workdir: Path, basedir: Path) -> list[tuple[str, bool, str]]
                             deterministic checks; basedir is an untouched copy of the starting state.
                             A run passes only if every check passes.

and may define:

    solve(task, workdir: Path) -> None     a reference solution, used by `pairedtest oracle`
    skills_dir(condition, model) -> Path   when skills depend on the model (e.g. self-written skills)
    GIT_IDENTITY = ("Name", "email")       placeholder identity for the agent's throwaway home
    AGENT_PATH = ["/path/to/bin"]          extra PATH entries the agent needs (e.g. a venv with pytest)

See template/suite/suite.py for a complete small example.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REQUIRED = ("TASKS", "SKILLS", "prepare", "verify")


def load(path: str | Path):
    p = Path(path).resolve()
    f = p / "suite.py" if p.is_dir() else p
    if not f.exists():
        raise SystemExit(f"no suite.py in {p}")
    sys.path.insert(0, str(f.parent))  # let the suite import its own modules
    name = f"pairedtest_suite_{abs(hash(str(f)))}"
    spec = importlib.util.spec_from_file_location(name, f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    missing = [k for k in REQUIRED if not hasattr(mod, k)]
    if missing:
        raise SystemExit(f"{f}: missing {', '.join(missing)} (see pairedtest/suite.py)")
    return mod


def skills_for(suite, condition: str, model: str) -> Path | None:
    if condition == "none":
        return None
    if hasattr(suite, "skills_dir"):
        return suite.skills_dir(condition, model)
    if condition not in suite.SKILLS:
        raise SystemExit(f"unknown condition {condition!r}; the suite has: none, {', '.join(suite.SKILLS)}")
    return Path(suite.SKILLS[condition])

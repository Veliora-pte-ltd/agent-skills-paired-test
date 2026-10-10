"""A complete, small pairedtest suite. Copy this directory and replace the fixture, tasks, checks
and skills with your own:

    python -m pairedtest oracle template/suite        # checks the checkers; no model calls
    python -m pairedtest plan   template/suite --models claude-sonnet-5-5 --repeats 5
    python -m pairedtest run    template/suite --models claude-sonnet-5-5 --repeats 5 --out results-adr --budget 2

The house rule tested here is deliberately one the agent cannot read off the repository: every
existing ADR says "Accepted", but a new one must say "Proposed" (only the review accepts it).
That is the kind of decision a skill exists to carry.
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
SKILLS = {"compact": HERE / "skills" / "compact"}   # add e.g. "long": HERE / "skills" / "long"
GIT_IDENTITY = ("Sam Developer", "sam@example.com")


@dataclass(frozen=True)
class Task:
    id: str
    family: str
    prompt: str        # phrased the way a developer would type it; never mentions the rules
    title: str         # what the checker expects (the agent never sees this)
    slug_words: tuple  # words the file name should contain


TASKS = {t.id: t for t in [
    Task("adr-postgres", "adr", "We decided to move from SQLite to Postgres for the hosted version. Write that up.",
         "Move to Postgres for the hosted version", ("postgres",)),
    Task("adr-queue", "adr", "Document our decision to send emails through a background job queue.",
         "Send emails through a background job queue", ("queue",)),
]}


def _git(wd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Example Dev", "-c", "user.email=dev@example.com", *args],
                   cwd=wd, check=True, capture_output=True)


def prepare(task: Task, workdir: Path, skills_dir: Path | None = None) -> None:
    """Fresh copy of the fixture as a git repository, plus the skills for this condition."""
    shutil.copytree(FIXTURE, workdir)
    _git(workdir, "init", "-q", "-b", "main")
    _git(workdir, "add", "-A")
    _git(workdir, "commit", "-q", "-m", "Initial state")
    if skills_dir is not None:
        shutil.copytree(skills_dir, workdir / ".claude" / "skills")
        _git(workdir, "add", "-A")
        _git(workdir, "commit", "-q", "-m", "Add team skills")


def verify(task: Task, wd: Path, base: Path) -> list[tuple[str, bool, str]]:
    """Deterministic checks. A run passes only if all of them pass."""
    out = []
    add = lambda name, ok, detail="": out.append((name, bool(ok), str(detail)))
    adr, badr = wd / "docs" / "adr", base / "docs" / "adr"
    old = {p.name for p in badr.glob("[0-9]*.md")}
    new = sorted(p for p in adr.glob("*.md") if p.name not in old and p.name != "README.md")
    add("one_new_adr", len(new) == 1, [p.name for p in new])
    if len(new) != 1:
        return out
    f = new[0]
    text = f.read_text()
    add("file_name", re.fullmatch(r"0003-[a-z0-9]+(-[a-z0-9]+)*\.md", f.name), f.name)
    add("file_name_topic", any(w in f.name for w in task.slug_words), f.name)
    add("title_line", re.match(r"# 3\. \S", text), text.splitlines()[:1])
    today = {dt.date.today().isoformat(), dt.datetime.now(dt.timezone.utc).date().isoformat()}
    add("date_today", any(f"Date: {d}" in text for d in today), "")
    add("status_proposed", re.search(r"(?m)^Status: Proposed\s*$", text), "")
    heads = re.findall(r"(?m)^## (.+?)\s*$", text)
    add("sections", heads == ["Context", "Decision", "Consequences"], heads)
    index = (adr / "README.md").read_text()
    add("index_row", re.search(rf"(?m)^\| \[0003\]\({re.escape(f.name)}\) \| .+ \| Proposed \|$", index), "")
    unchanged = all((adr / n).read_text() == (badr / n).read_text() for n in old)
    add("existing_adrs_unchanged", unchanged, "")
    return out


def solve(task: Task, wd: Path) -> None:
    """Reference solution: `pairedtest oracle` checks that it passes and that an untouched repo fails."""
    slug = re.sub(r"[^a-z0-9]+", "-", task.title.lower()).strip("-")
    name = f"0003-{slug}.md"
    (wd / "docs/adr" / name).write_text(
        f"# 3. {task.title}\n\nDate: {dt.date.today().isoformat()}\nStatus: Proposed\n\n"
        "## Context\n\nWhy this came up.\n\n## Decision\n\nWhat we will do.\n\n## Consequences\n\nWhat changes.\n")
    idx = wd / "docs/adr/README.md"
    idx.write_text(idx.read_text() + f"| [0003]({name}) | {task.title} | Proposed |\n")

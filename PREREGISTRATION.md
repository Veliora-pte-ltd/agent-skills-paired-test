# Pre-registration: do Agent Skills pay for themselves?

Written 8 October 2026, before any experimental runs (smoke tests excepted).

## Question

On a fixed set of tasks that depend on in-house conventions, does giving a coding agent a SKILL.md
change its pass rate, cost and time? Does a compact skill do better than a comprehensive one carrying
the same rules? Does a skill the agent writes for itself from the repository help? Does the skill load
when it should and stay out of the way when it shouldn't?

## Tasks

12 tasks in one small Python repository (`fixture/tillroll`), in two families of six:
database migrations with house conventions, and cutting a release with house rules for versioning,
changelog and release metadata. The prompts are phrased as a developer would type them and never
mention the conventions. Each task has a deterministic verifier (`skill_ab/verify.py`) with 10 to 14
checks. A run passes only if every check passes.

## Conditions

- `none`: no skills installed.
- `compact`: two short skills (about 270 to 290 words each).
- `comprehensive`: the same rules in two long, wiki-style skills (about 1,450 to 2,200 words each),
  with background, worked examples, troubleshooting and FAQs. Same `name` and `description`.
- `selfgen`: two skills written by the same model after studying the repository (one run per skill).

In every skill condition both skills are installed, so the agent has to pick the relevant one.

## Agent and models

Claude Code (headless, `claude -p --output-format stream-json`), project settings only, web tools
disabled, permissions bypassed inside a throwaway copy of the repository. Models chosen to fit a hard
budget of US$30 for the whole article (the harness stops at US$27).

## Primary metric

Pass rate (all checks pass) per condition, paired by task and repeat against `none`.

## Secondary metrics

Mean fraction of checks passed; cost per run and per passed run (computed from the token usage the
API returns times the published price list); input, cache and output tokens; wall time; number of
agent turns; whether a skill was loaded (Skill tool call or SKILL.md read).

## Trigger test

20 prompts that should load one of the compact skills and 20 that should not, run with read-only
tools and a small turn limit. Measure trigger rate and false-trigger rate.

## Analysis

Wilson 95% intervals for pass rates. Differences against `none` with a 95% cluster bootstrap over
tasks (10,000 resamples). With 12 tasks, differences smaller than roughly 20 to 30 percentage points
are not expected to be distinguishable from noise; results will be reported as such.

## Amendment (8 October 2026, before the reported runs)

A first batch (54 Haiku runs, a 12-run no-skill pilot and two self-generated skills per model) was
discarded. Reading the transcripts showed two fixture faults rather than agent behaviour:
(1) the changelog listed fixes that did not exist in the code, so a careful agent refused to release;
(2) the release history contradicted the house versioning rule (1.4.2 was a patch release with an
`Added` entry). The fixture now has real commits behind every changelog entry and a history that is
consistent with the rule. Tasks, prompts, skills, verifiers and metrics are otherwise unchanged. The
discarded records are kept in `results/discarded-v1/` and their cost is included in the total.

A second partial batch (22 runs) was also discarded: the harness had cached the old starting state
for the verifier, so it compared new runs against the pre-fix fixture. The cache is now rebuilt at
the start of every invocation. Records are in `results/discarded-v2/`; cost is included in the total.

A third batch (all 240 Haiku runs and 35 Sonnet runs) was set aside after reading the final messages:
the agent's sandbox had no git identity, so `git commit` failed and the agent often stopped to ask who
to commit as. A developer machine has an identity, so this was an environment artefact. Each run now
gets a `~/.gitconfig` with a placeholder name and email. The Haiku records are kept in
`results/discarded-v3-no-git-identity/` and are reported as a sensitivity check, not as the main
result; their cost is included in the total.

During the reported Sonnet batch, starting the Haiku trigger test cleared the verifier's cached
starting state once (13:00 BST); it was rebuilt from the same fixture on next use. I read the checks of
every run verified within a minute of the reset; all failures matched what the agent said it had done,
so no run was excluded.

## Additions not in the original plan

- Two extra analyses, added after seeing the data and labelled as such in the write-up: pass rate with
  the "no git tag" check ignored, and the set-aside no-git-identity batch.
- A small Claude Opus 5.5 spot check (`none` and `compact` only, 2 repeats), run only if the budget
  allowed after the planned runs. It is exploratory.

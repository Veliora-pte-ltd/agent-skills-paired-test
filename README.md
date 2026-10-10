# agent-skills-paired-test

A small harness for testing whether an Agent Skill (a `SKILL.md` file) earns its place: run a coding agent on your own tasks with and without the skill, score every run with a scripted checker, and compare the two task by task. It also holds the code and all the kept data from the test behind Veliora's note on whether Agent Skills pay for themselves: Claude Code on 12 tasks, with no skill, a short skill, a long skill and a self-written one.

Written up at https://veliora.works/engineering/do-agent-skills-pay-for-themselves/ ("Do Agent Skills pay for themselves? A paired test of SKILL.md on real tasks").

On tasks that depended on house rules the repository did not show, a short skill took Claude Opus 5.5 from 6 of 24 passing runs to 24 of 24, and Claude Sonnet 5.5 from 10 of 30 to 30 of 30, and made runs cheaper. Where the rules could be read off the existing files, the skill changed nothing. A skill the agent wrote for itself made things worse. Your tasks will differ, which is why the harness is here.

- [Test your own skill](#test-your-own-skill)
- [Results (runs of 8 October 2026)](#results-runs-of-8-october-2026)
- [How this was tested](#how-this-was-tested)
- [Reproduce](#reproduce)
- [What is not in this repository (to be re-run)](#what-is-not-in-this-repository-to-be-re-run)
- [Repository layout](#repository-layout)

## Test your own skill

The test is simple. Take a dozen tasks your team really does, phrased the way people actually ask for them. Write a script that checks each result, then run each task with no skill and with the skill a few times. The skill earns its place if it raises the share of runs that pass every check, or cuts the cost, and nothing gets worse.

Requirements: Python 3.11 or later (3.13 was used), git, and Claude Code (`npm install -g @anthropic-ai/claude-code`; 2.1.293 was used). The `pairedtest` package uses only the standard library. Docker is not needed.

**1. Copy the template suite.** `template/suite/` is a complete small suite: a fixture repository, two tasks, a checker, reference solutions and one skill. It tests a rule the repository cannot teach: every existing ADR (architecture decision record) says `Accepted`, but a new one must say `Proposed`.

```sh
git clone https://github.com/Veliora-pte-ltd/agent-skills-paired-test.git
cd agent-skills-paired-test
cp -r template/suite my-suite
```

**2. Make it yours.** In `my-suite/suite.py`:

- `fixture/`: a small copy of your repository, or the part of it the tasks touch.
- `TASKS`: each task's `prompt`, written the way a developer would type it. Don't mention the rules the skill teaches, because the point is to see whether the skill supplies them.
- `verify(task, workdir, basedir)`: deterministic checks that return `(name, passed, detail)`. A run passes only if every check passes. Check the outcome (the file exists, the test passes, the hash matches), not the wording.
- `solve(task, workdir)`: a reference solution for each task.
- `SKILLS`: the conditions to compare, e.g. `{"compact": ..., "long": ...}`. Each points to a directory of skills, which are installed at `.claude/skills/` in the run's copy. `none` is always included. `template/SKILL.md` is a starting structure: a fast path, the rules that can't be inferred from the code, and what's out of scope.

The suite interface is documented in `pairedtest/suite.py`. `skill_ab/suite.py` shows the same interface wrapping the 12-task experiment below.

**3. Check the checkers.** This makes no model calls. Every reference solution must pass and every untouched repository must fail:

```sh
python3 -m pairedtest oracle my-suite
```

**4. Plan and run.** `plan` prints the run list without calling a model. `run` runs it.

```sh
python3 -m pairedtest plan my-suite --models claude-sonnet-5-5 --repeats 5
export ANTHROPIC_API_KEY=...        # passed only to the Claude Code child process, never written to disk
python3 -m pairedtest run my-suite --models claude-sonnet-5-5 --repeats 5 --out results-mine --budget 5 --cap 0.50
```

- **Budget guard.** Before each run, the spend ledger (`results-mine/spend.jsonl`) plus the caps of the runs in flight must stay under `--budget` (US$), or the batch stops. Each run is also capped with Claude Code's `--max-budget-usd` (`--cap`).
- **Cost.** Cost is the token counts the API reports times the list prices in `pairedtest/pricing.py`, which were read on 8 October 2026. Pass `--prices prices.json` when prices change. For a model with no price, Claude Code's own estimate is used, and the run's record says so.
- **Subscription instead of an API key.** Use `--auth subscription --config-dir DIR --cap 0`, after signing in once with `CLAUDE_CONFIG_DIR=DIR claude auth login`. Every API-key variable is removed from the child environment. Costs are then Claude Code's estimates. The batch stops at the first usage-limit, sign-in or API error.
- **Isolation and resuming.** Each run gets a fresh copy of the repository and a throwaway home directory with a placeholder git identity. It runs with `--setting-sources project` and web tools disabled, so your own Claude Code settings, skills and memory are never used. The plan is shuffled in repeat-major blocks, so a batch that stops early is still balanced. Re-running the same command skips runs that were already scored.

**5. Read the result.** This makes no model calls:

```sh
python3 -m pairedtest report results-mine/runs.jsonl --json results-mine/summary.json
```

You get pass rates with 95% Wilson intervals, the change against no skill in percentage points averaged over tasks with a 95% bootstrap interval over tasks, a sign-flip permutation p-value, cost per run and per passing run, how often a skill loaded, per-task counts and the checks that failed. Read the task-level interval, not the run-level one: five repeats of one task are not five independent samples. With a dozen tasks, expect to detect only large differences.

Things the published test found worth doing when you write the skill itself: write it for decisions, not for procedures the code already shows; keep it short; say what not to do; and don't ship a skill the agent wrote for itself without reviewing it. Testing on your own cases before launch and after every change is also how Veliora builds applied AI workflows: https://veliora.works/applied-ai/.

## Results (runs of 8 October 2026)

All runs took place on 8 October 2026, with Claude Code 2.1.293 headless (`claude -p`). The models were Claude Opus 5.5 (`claude-opus-5-5`), Claude Sonnet 5.5 (`claude-sonnet-5-5`) and Claude Haiku 5.5 (`claude-haiku-5-5`). The tasks are 6 database-migration tasks and 6 release tasks in `fixture/tillroll`, a small Python service written for the test. The conditions are no skill, a compact skill (268 to 291 words), a comprehensive skill with the same rules (1,458 to 2,195 words) and a skill the model wrote for itself (516 to 977 words). Every figure below is in `results/summary.json` or `results/subscription-summary.json`, and `checks/verify_note.py` checks it against the note.

Runs passing every check:

| Model | Condition | Release tasks | Migration tasks | All (95% Wilson) | vs no skill, points (95% bootstrap over tasks) |
|---|---|---|---|---|---|
| Opus 5.5* | No skill | 6/24 | not run | – | – |
| | Compact | 24/24 | not run | – | +75 (+42 to +100), release only |
| Sonnet 5.5 | No skill | 10/30 | 30/30 | 67% (54%–77%) | – |
| | Compact | 30/30 | 30/30 | 100% (94%–100%) | +33 (+8 to +58) |
| | Comprehensive | 30/30 | 30/30 | 100% (94%–100%) | +33 (+8 to +58) |
| | Self-written | 0/30 | 25/30 | 42% (30%–54%) | −25 (−50 to 0) |
| Haiku 5.5 | No skill | 5/30 | 29/30 | 57% (44%–68%) | – |
| | Compact | 29/30 | 28/30 | 95% (86%–98%) | +38 (+10 to +67) |
| | Comprehensive | 30/30 | 28/30 | 97% (89%–99%) | +40 (+10 to +68) |
| | Self-written | 0/30 | 22/30 | 37% (26%–49%) | −20 (−43 to 0) |

\*Opus 5.5 ran only the 6 release tasks, with no skill and the compact skill, 4 repeats each, on a Claude Pro subscription. Sonnet and Haiku ran all 12 tasks in all four conditions, 5 repeats each, on the API.

- **Releases (rules the repository did not show).** Two of the release rules can't be inferred from the repository at all: CI creates tags, so nobody tags by hand, and a Changed entry means a minor version. Without a skill, 14 of 24 Opus release runs and 15 of 30 Sonnet runs created a git tag. Every failed Opus run broke exactly one rule.
- **Migrations (rules visible in the existing files).** No measurable effect. Sonnet passed 30 of 30 runs without a skill, and Opus passed 12 of 12 in a smaller exploratory check on the API.
- **Cost.** On Sonnet, the compact skill cut cost by 0.58 US cents a run (14%; 95% interval 0.40 to 0.75) at published API prices, mostly through shorter output. On Opus, Claude Code's own estimate fell from 17.5 to 13.1 cents a run (25%). That figure is an estimate from subscription runs, not an API bill, so it isn't comparable with the Sonnet figure. The comprehensive skill cost Sonnet 0.31 cents a run more than no skill (about 7%) for the same pass rate.
- **Self-written skills.** These were 0 of 30 release runs on both Sonnet and Haiku. They turned a habit visible in the history (a hand-made `v1.4.2` tag) into an instruction, and added "ask the user first" steps that stall a headless run.
- **Loading.** The relevant skill loaded in every skill run on every model. In a separate trigger test, Sonnet and Haiku loaded a skill for 20 of 20 prompts that needed one and for none of 20 that did not.
- **Spend.** US$23.17 in API usage for everything, including set-aside batches (`results/spend.jsonl`). The 48 Opus subscription runs were covered by the plan, with a Claude Code estimate of US$7.35.

Limitations, as in the note:

- The test used one small synthetic repository, and its release rules were chosen to be invisible. The effect size reflects that choice.
- There are only 12 tasks, so task-level tests have little power. The permutation p-value for the compact skill is 0.06 on Opus, 0.12 on Sonnet and 0.04 on Haiku.
- Opus ran on release tasks only, and Fable 5.1 was not run at all.
- Only Claude Code and Claude models were tested.
- In the comprehensive skills, length is confounded with worked examples.
- The self-written skills were generated once per model.
- The trigger test watched only four turns with two clearly separated skills.
- All runs were headless.
- Three earlier batches were set aside for environment faults. `PREREGISTRATION.md` documents them, and they are kept in `results/discarded-*`.

## How this was tested

- **Design, written before the runs:** `PREREGISTRATION.md` covers the question, conditions, metrics and analysis, plus dated amendments and the analyses added after seeing the data.
- **Runs:** `skill_ab/run.py` ran the API runs, six at a time, and wrote `results/main.jsonl`, `results/trigger.jsonl`, `results/selfgen.jsonl` and `results/spend.jsonl`. `skill_ab/run_sub.py` ran the Opus subscription runs one at a time, with no API key in the environment, and wrote `results/subscription-rerun.jsonl`. The reusable `pairedtest` package was generalised from these two scripts after the runs. It was not used to produce the published numbers.
- **Scoring:** `skill_ab/verify.py` has 10 to 14 checks per task. `skill_ab/oracle.py` holds the reference solutions: every task must pass with its reference solution and fail when left untouched.
- **Analysis:** `skill_ab/analyse.py` and `skill_ab/analyse_sub.py` write `results/summary.{json,md}` and `results/subscription-summary.{json,md}`. Charts come from `skill_ab/charts_lead.py` (the three charts in the note: `charts/pass-rate-models`, `misses-models` and `cost-models`) and `charts.py` / `charts_sub.py` (charts from earlier versions of the note).
- **Number check:** `checks/verify_note.py` renders 125 phrases from the results files and requires each to appear word for word in the live note. It then requires every number written in digits in the note (642 of them, including tables and chart descriptions) to sit inside a checked phrase. The only exceptions are a short, listed set of set-up facts and outside sources, such as the SkillsBench figures and the specification's 5,000-token guidance. On 10 October 2026 the check found all 125 phrases and left 0 numbers unchecked.
- **Tests:** `python3 -m unittest discover -s tests` runs 20 tests with no model calls. They cover: the statistics and the report reproducing `results/summary.json` and the Opus paired result exactly; both suites' oracles; stream parsing and stop rules; end-to-end runs of the runner against a fake `claude` (`tests/fake_claude.py`), covering pass/fail scoring, the budget stop, resuming, the API key never being saved, subscription mode carrying no key, and the stop at a usage limit; and a scan of every published file, transcripts included, for credentials, personal addresses and machine paths.

## Reproduce

From the repository root:

```sh
python3 -m unittest discover -s tests           # 20 tests, no model calls
python3 checks/verify_note.py                   # the live note against the results files
python3 -m pairedtest oracle skill_ab           # all 12 checkers pass a reference solution and fail an untouched repo
cd skill_ab && python3 analyse.py && python3 analyse_sub.py   # rewrites results/summary.* and subscription-summary.*, byte for byte
python3 charts_lead.py                          # charts/*.png and *.svg (needs requirements.txt: matplotlib, numpy)
```

`analyse.py` and `analyse_sub.py` read only files in this repository, and they reproduce the published summaries exactly. You can check this with `git diff --stat results/` after running them.

To run the experiment again, with your own key and your own ledger:

```sh
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export NODE_BIN_DIR="$(dirname "$(command -v claude)")"   # node 22 and claude
export AGENT_VENV_BIN="$PWD/.venv/bin"                    # python3 and pytest for the agent
mv results results-2026-10-08 && mkdir results
cd skill_ab
python3 oracle.py
python3 run.py selfgen --model claude-sonnet-5-5          # overwrites skills/self-generated/<model>
python3 run.py main --model claude-sonnet-5-5 --repeats 5 --budget 5
python3 run.py trigger --model claude-sonnet-5-5 --max-turns 4
python3 analyse.py
```

Alternatively, use the reusable runner on the same suite: `python3 -m pairedtest run skill_ab --models claude-sonnet-5-5 --repeats 5 --out results-mine --path "$NODE_BIN_DIR" --budget 5`.

## What is not in this repository (to be re-run)

- **Fable 5.1.** It was planned alongside Opus, but it didn't run. The first run was refused before any tokens were used ("You're out of usage credits"; recorded in `results/subscription-rerun.jsonl`), so there are no Fable results. **To be re-run.**
- **Opus on the rest of the grid.** Opus wasn't run with the comprehensive or self-written skills, and the migration tasks only got the exploratory check (2 repeats, which stopped at 47 of 48 runs when the budget guard tripped). **To be re-run.**
- **Identical re-runs.** Model output isn't deterministic, model versions and prices change, and Claude Code 2.1.293 may no longer be the version you get. A new run is a new dated result, not a check of these numbers run for run. The numbers can be checked from the kept data (see [Reproduce](#reproduce)).
- **Killed runs.** `results/spend.jsonl` includes 6 rows (US$0.36 in total) that are estimates for runs stopped before they reported a cost. These have no transcripts.
- **Credentials and the subscription login.** These are left out by design.
- **Edits to the published files.** In the transcripts, the directory the harness ran from is replaced with `<harness>`, the machine's user and host name in git's error message with `user@host`, and the subscription config directory with `<claude-config>`. Account-level usage fields, such as plan-utilisation windows and payment flags, are removed from the subscription records. In `skill_ab/run_sub.py`, two comments and the list of API-key variable names removed from the child environment were tidied. Nothing that any number depends on was changed, and the tests confirm the summaries still reproduce exactly.

## Repository layout

```text
pairedtest/                reusable harness: suite loader, runner, stream parser, statistics, report, CLI
template/SKILL.md          a SKILL.md starting structure (fast path, rules not in the code, out of scope)
template/suite/            a complete small suite to copy: fixture, tasks, checks, reference solutions, skill
skill_ab/                  the experiment as run: tasks, checker, oracle, runners, analysis, charts; suite.py adapter
fixture/tillroll/          the test repository every run started from
skills/                    compact, comprehensive and self-written skills exactly as used
trigger_prompts.json       20 prompts that should load a skill and 20 that should not
results/                   one JSON line per run, gzipped transcripts, the spend ledger, summaries
results/discarded-*        batches set aside for environment faults (see PREREGISTRATION.md)
charts/                    the note's charts (Figtree font under the SIL Open Font Licence, charts/fonts/OFL.txt)
checks/verify_note.py      every number in the note against the results files
tests/                     unittest suite and a fake claude binary
PREREGISTRATION.md         question, conditions, metrics and analysis, written before the runs
```

The code is MIT licensed (see `LICENSE`).

---

Maintained by Veliora (https://veliora.works/)

"""Check every number in the published note against the data in this repository. No model calls.

Each phrase below is rendered FROM the results files and must appear verbatim in the note. Then every
number written in digits in the note (body, tables and chart descriptions) must sit inside a checked
phrase, or inside a phrase listed under CONTEXT: numbers that describe the set-up or quote an outside
source rather than results. Anything left over is reported as unchecked.

Run from the repository root:
    python3 checks/verify_note.py             # fetches the live note
    python3 checks/verify_note.py page.html   # or checks a saved copy
Exit code 0 only if every phrase is found and no number is left unchecked.
"""
from __future__ import annotations

import html
import json
import re
import statistics as st
import sys
import urllib.request
from collections import Counter
from pathlib import Path

NOTE_URL = "https://veliora.works/engineering/do-agent-skills-pay-for-themselves/"
ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
S = json.loads((R / "summary.json").read_text())
SUB = json.loads((R / "subscription-summary.json").read_text())
load = lambda f: [json.loads(l) for l in (R / f).read_text().splitlines() if l.strip()]
MAIN = [r for r in load("main.jsonl") if "passed" in r]
SUBR = [r for r in load("subscription-rerun.jsonl") if "passed" in r]
SPEND = load("spend.jsonl")
TRIG = load("trigger.jsonl")
SELFGEN = load("selfgen.jsonl")

if len(sys.argv) > 1:
    page = Path(sys.argv[1]).read_text()
else:
    req = urllib.request.Request(NOTE_URL, headers={"User-Agent": "agent-skills-paired-test-verify/1.0"})
    page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
main_html = re.search(r"<main.*?</main>", page, re.S).group(0)
T = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main_html)))
T = re.sub(r" ([,.;:)])", r"\1", T).replace("( ", "(")
T += " || " + " || ".join(html.unescape(a) for a in re.findall(r'alt="([^"]+)"', main_html))  # chart descriptions

H, SN, O = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
NAME = {H: "Haiku 5.5", SN: "Sonnet 5.5", O: "Opus 5.5"}
CONDS = ["none", "compact", "comprehensive", "selfgen"]
CLABEL = {"none": "No skill", "compact": "Compact", "comprehensive": "Comprehensive", "selfgen": "Self-written"}
M = S["models"]
OS = SUB["subscription"][O]
ON, OC = OS["conditions"]["none"], OS["conditions"]["compact"]
rel = lambda m, c: M[m]["families"]["release"][c]
mig = lambda m, c: M[m]["families"]["migration"][c]
cond = lambda m, c: M[m]["conditions"][c]
pair = lambda m, c, k="all": M[m]["paired"][c][k]
r100 = lambda x: round(x * 100)
pc = lambda x: f"{r100(x)}%"
wil = lambda w: f"{pc(w[0])}–{pc(w[1])}"
pts = lambda x: ("+" if r100(x) > 0 else ("−" if r100(x) < 0 else "")) + str(abs(r100(x)))
ci_pts = lambda c: f"{pts(c[0])} to {pts(c[1])}"
cents = lambda x, d=2: f"{x * 100:.{d}f}"
d1 = lambda x: f"{x:.1f}"
n_ = lambda x: f"{x:,}"
kfmt = lambda x: f"{round(x / 1000)}k"
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]

checks, problems = {}, []


def need(label: str, phrase: str) -> None:
    checks[label] = (phrase, phrase in T)


def ensure(label: str, ok: bool) -> None:
    """A fact about the data that the phrase alone cannot show (e.g. two values that must agree)."""
    if not ok:
        problems.append(label)


def ofk(k, n): return f"{k} of {n}"


# ---------------------------------------------------------------- run counts
n_main_api = sum(cond(m, c)["n"] for m in (H, SN) for c in CONDS)
expl_n = cond(O, "none")["n"] + cond(O, "compact")["n"]
sub_n = ON["n"] + OC["n"]
need("tested-with runs", f"{sub_n} Opus runs and {n_main_api} Sonnet and Haiku runs (12 tasks × 4 conditions × 5 repeats × 2 models), "
     f"plus {expl_n} exploratory Opus runs on the API and {len(TRIG)} trigger-test runs")
ensure("480 = 12 x 4 x 5 x 2", n_main_api == 12 * 4 * 5 * 2 and len({r["task"] for r in MAIN}) == 12)
ensure("Opus: 6 release tasks x 2 conditions x 4 repeats", sub_n == 6 * 2 * 4 and {r["rep"] for r in SUBR} == {0, 1, 2, 3})
need("tested-with opus", "claude-opus-5-5: 6 release tasks, no skill and compact skill, 4 repeats, Claude Pro subscription")
need("tested-with sonnet/haiku", "claude-sonnet-5-5 and claude-haiku-5-5: all 12 tasks, four conditions, 5 repeats, API")
ensure("5 repeats", {r["rep"] for r in MAIN if r["model"] in (H, SN)} == {0, 1, 2, 3, 4})
versions = {r.get("claude_code_version") for r in MAIN + SUBR}
need("Claude Code version", f"Claude Code {versions.pop()}, headless"); ensure("one Claude Code version", not versions)
need("methods version", "Claude Code 2.1.293 headless")
need("run date", "Run date 8 October 2026")
spend = sum(r["cost_usd"] for r in SPEND)
need("spend", f"US${spend:.2f} in API usage for everything, including set-aside batches")
need("opus estimate tested-with", f"(Claude Code estimate: US${OS['cost_estimate_total']:.2f})")
need("opus estimate body", f"the {sub_n} runs add up to US${OS['cost_estimate_total']:.2f}")
cost480 = sum(r["cost_usd"] for r in MAIN if r["model"] in (H, SN))
need("480 runs cost", f"The {n_main_api} Sonnet and Haiku runs cost about US${cost480:.2f} at published prices")
need("exploratory 47 of 48", f"stopped it one run short, at {expl_n} of {expl_n + 1}")
need("exploratory (47 runs", f"({expl_n} runs; the spending guard stopped one short)")
need("trigger 40 prompts", f"Separately, {len(TRIG) // 2} prompts were run with read-only tools and a four-turn limit: "
     f"{sum(1 for r in TRIG if r['model'] == SN and r['kind'] == 'should_trigger')} that should load")
need("trigger 20 should not", f"and {sum(1 for r in TRIG if r['model'] == SN and r['kind'] == 'should_not_trigger')} that should not")

# ---------------------------------------------------------------- skills
wc = lambda p: len(p.read_text().split())
SK = ROOT / "skills"
cw = [wc(p) for p in (SK / "compact").glob("*/SKILL.md")]
lw = [wc(p) for p in (SK / "comprehensive").glob("*/SKILL.md")]
sw = [wc(p) for p in (SK / "self-generated").glob("*/*/SKILL.md")]
need("compact words", f"{min(cw)}–{max(cw)} words")
need("comprehensive words", f"{n_(min(lw))}–{n_(max(lw))} words")
need("self-written words", f"{min(sw)}–{max(sw)} words")
need("about 270 words", "short (about 270-word) skill"); ensure("about 270 words", abs(st.mean(cw) - 270) < 15)
ratios = sorted(l / c for l, c in zip(sorted(lw), sorted(cw)))  # same skill pairs: release 1,458/268, migrations 2,195/291
ensure("five to seven times (word ratios)", 5 <= int(ratios[0]) and int(ratios[-1]) <= 7)
need("selfgen one run per skill", "one run per skill"); ensure("selfgen one run per skill", Counter((r["model"], r["skill"]) for r in SELFGEN) == Counter({(m, s): 1 for m in (H, SN) for s in ("db-migrations", "release")}))
nchk = Counter(len(r["checks"]) for r in MAIN)
need("10 to 14 checks", f"Every task has a checker with {min(nchk)} to {max(nchk)} checks")

# ---------------------------------------------------------------- TL;DR and opening
need("dek opus", f"Opus followed every rule in {ON['passed']} of {ON['n']} runs without a skill and in {OC['passed']} of {OC['n']} with a short one; "
     f"Sonnet went from {rel(SN, 'none')['passed']} of {rel(SN, 'none')['n']} to {rel(SN, 'compact')['passed']} of {rel(SN, 'compact')['n']}")
need("tldr release", f"Claude Opus 5.5 followed every house rule in {ON['passed']} of {ON['n']} runs and Claude Sonnet 5.5 in {rel(SN, 'none')['passed']} of {rel(SN, 'none')['n']}")
need("tldr release skill", f"skill: {OC['passed']} of {OC['n']} and {rel(SN, 'compact')['passed']} of {rel(SN, 'compact')['n']}")
need("tldr migrations", f"Sonnet passed {mig(SN, 'none')['passed']} of {mig(SN, 'none')['n']} runs without a skill, and Opus {mig(O, 'none')['passed']} of {mig(O, 'none')['n']} in a smaller exploratory check")
sn_cut = 1 - cond(SN, "compact")["cost_mean"] / cond(SN, "none")["cost_mean"]
op_cut = 1 - OC["cost_mean"] / ON["cost_mean"]
comp_up = cond(SN, "comprehensive")["cost_mean"] / cond(SN, "none")["cost_mean"] - 1
need("tldr sonnet 14%", f"On Sonnet, {pc(sn_cut)} less per run at API prices")
need("tldr opus 25%", f"Claude Code's own estimate fell {pc(op_cut)} per run")
need("tldr comprehensive 7%", f"cost {pc(comp_up)} more than no skill")
need("tldr selfgen 0 of 30", f"passed {rel(SN, 'selfgen')['passed']} of {rel(SN, 'selfgen')['n']} release runs")
tr = S["trigger"]
need("tldr trigger", f"Sonnet loaded a skill for {tr[SN]['pos_triggered']} of {tr[SN]['pos_n']} prompts that needed one and for none of {tr[SN]['neg_n']} that did not")
ensure("trigger: no false loads", tr[SN]["neg_triggered"] == 0 and tr[H]["neg_triggered"] == 0)
h_cut = 1 - cond(H, "compact")["cost_mean"] / cond(H, "none")["cost_mean"]
need("tldr haiku", f"{rel(H, 'none')['passed']} of {rel(H, 'none')['n']} release runs passed without a skill and {rel(H, 'compact')['passed']} of {rel(H, 'compact')['n']} with the short one, at {pc(h_cut)} lower cost per run")

# ---------------------------------------------------------------- main results table
need("table opus none", f"Opus 5.5* No skill {ON['passed']}/{ON['n']} not run – –")
po = OS["paired_compact"]
need("table opus compact", f"Compact {OC['passed']}/{OC['n']} not run – {pts(po['diff'])} ({ci_pts(po['ci'])}), release only")
for m in (SN, H):
    for c in CONDS:
        a = cond(m, c)
        row = f"{CLABEL[c]} {rel(m, c)['passed']}/{rel(m, c)['n']} {mig(m, c)['passed']}/{mig(m, c)['n']} {pc(a['pass_rate'])} ({wil(a['wilson'])})"
        if c == "none":
            row = f"{NAME[m]} {row} –"
        else:
            p = pair(m, c)
            row += f" {pts(p['diff'])} ({ci_pts(p['ci'])})"
        need(f"table {NAME[m]} {c}", row)

# ---------------------------------------------------------------- three things
need("opus 6 to 24, sonnet 10 to 30", f"took Opus from {ON['passed']} to {OC['passed']} passing runs out of {OC['n']} and Sonnet from {rel(SN, 'none')['passed']} to {rel(SN, 'compact')['passed']} out of {rel(SN, 'compact')['n']}")
psr = pair(SN, "compact", "release")
need("+75 / +67", f"that is {pts(po['diff'])} points for Opus (95% interval {ci_pts(po['ci'])}) and {pts(psr['diff'])} for Sonnet ({ci_pts(psr['ci'])})")
pt = M[SN]["per_task"]
ceil_tasks = sum(1 for t, v in pt.items() if t.startswith("rel") and v["none"][0] == v["none"][1])
need("sonnet ceiling two of six", f"it already passed {WORDS[ceil_tasks]} of the six release tasks every time")
need("visible: sonnet 30/30 opus 12/12", f"Sonnet passed {mig(SN, 'none')['passed']} of {mig(SN, 'none')['n']} migration runs, and Opus {mig(O, 'none')['passed']} of {mig(O, 'none')['n']} in the exploratory check")
need("compact vs comprehensive 60/60", f"{cond(SN, 'compact')['passed']} of {cond(SN, 'compact')['n']} against {cond(SN, 'comprehensive')['passed']} of {cond(SN, 'comprehensive')['n']} on Sonnet")
phr = pair(H, "compact", "release")
need("haiku 5 to 29 +80", f"{rel(H, 'none')['passed']} to {rel(H, 'compact')['passed']} of {rel(H, 'compact')['n']} release runs with the compact skill ({pts(phr['diff'])} points, {ci_pts(phr['ci'])})")
need("haiku mig 29 of 30", f"{mig(H, 'none')['passed']} of {mig(H, 'none')['n']} migration runs without a skill")
need("haiku 57 vs 58", f"{cond(H, 'compact')['passed']} of {cond(H, 'compact')['n']} against {cond(H, 'comprehensive')['passed']} of {cond(H, 'comprehensive')['n']} for compact and comprehensive")

# ---------------------------------------------------------------- Opus section
need("opus 6 of 24 25% (12-45)", f"{ON['passed']} of {ON['n']} runs followed every house rule, {pc(ON['pass_rate'])} ({wil(ON['wilson'])}), against {rel(SN, 'none')['passed']} of {rel(SN, 'none')['n']} for Sonnet")
need("opus 24 of 24 100%", f"it passed {OC['passed']} of {OC['n']}, {pc(OC['pass_rate'])} ({wil(OC['wilson'])})")
need("opus +75 5 of 6", f"that is {pts(po['diff'])} points (95% interval {ci_pts(po['ci'])}), with {po['tasks_better']} of {po['tasks']} tasks improved and none worse"); ensure("opus none worse", po["tasks_worse"] == 0)
ofail = [r for r in SUBR if r["condition"] == "none" and not r["passed"]]
fails = Counter(tuple(c["name"] for c in r["checks"] if not c["ok"]) for r in ofail)
ensure("every failed Opus run broke exactly one rule", all(len(k) == 1 for k in fails))
need("opus 14 of 18 tag, other 4", f"{fails[('no_git_tag_created',)]} of the {len(ofail)} created a git tag, and the other {fails[('changelog_section_order',)]} were the security release")
ensure("the other 4 are all rel-06-security", all(r["task"] == "rel-06-security" for r in ofail if not next(c for c in r["checks"] if c["name"] == "changelog_section_order")["ok"]))
opt = OS["per_task"]
need("opus minor 4 of 4, major 2 of 4", f"Opus passed the minor release in {opt['rel-02-minor']['none'][0]} of {opt['rel-02-minor']['none'][1]} runs and the major release in {opt['rel-03-major']['none'][0]} of {opt['rel-03-major']['none'][1]}")
ensure("no run of the other four tasks", all(v["none"][0] == 0 for t, v in opt.items() if t not in ("rel-02-minor", "rel-03-major")))
need("opus estimate 17.5 to 13.1 (25% less)", f"fell from {cents(ON['cost_mean'], 1)} to {cents(OC['cost_mean'], 1)} cents per run ({pc(op_cut)} less)")
need("opus output tokens", f"output from {n_(round(ON['output_tokens_mean']))} to {n_(round(OC['output_tokens_mean']))} tokens")
need("opus median wall", f"the median run from {d1(ON['wall_median'])} to {d1(OC['wall_median'])} seconds")
ec_n, ec_c = cond(O, "none"), cond(O, "compact")
need("exploratory release 3/11 12/12", f"{rel(O, 'none')['passed']}/{rel(O, 'none')['n']} release runs passed without the skill and {rel(O, 'compact')['passed']}/{rel(O, 'compact')['n']} with it")
need("exploratory migrations 12/12", f"migrations passed {mig(O, 'none')['passed']}/{mig(O, 'none')['n']} either way"); ensure("exploratory migrations 12/12 both", (mig(O, "compact")["passed"], mig(O, "compact")["n"]) == (12, 12))
need("exploratory cost 11.2 to 7.9 (29%)", f"mean cost fell from {cents(ec_n['cost_mean'], 1)} to {cents(ec_c['cost_mean'], 1)} cents per run ({pc(1 - ec_c['cost_mean'] / ec_n['cost_mean'])} less)")
need("exploratory all 12 tasks two repeats", f"with Opus on all {len({r['task'] for r in MAIN if r['model'] == O})} tasks and two repeats")
need("exploratory two repeats", "Opus on all 12 tasks with no skill and the compact skill, two repeats each"); ensure("two repeats", {r["rep"] for r in MAIN if r["model"] == O} == {0, 1})

# ---------------------------------------------------------------- per-task table
SP = M[SN]["per_task"]; HP = M[H]["per_task"]
for t in sorted(SP):
    o = f"{opt[t]['none'][0]} {opt[t]['compact'][0]}" if t in opt else "– –"
    row = f"{t} {o} " + " ".join(str(SP[t][c][0]) for c in CONDS) + " " + " ".join(str(HP[t][c][0]) for c in CONDS)
    need(f"per-task {t}", row)

# ---------------------------------------------------------------- what goes wrong
chk = lambda m, c: M[m]["checks"][c]
need("tags 14 of 24, 15 of 30", f"{ON['failed_checks']['no_git_tag_created']} of {ON['n']} Opus release runs and {chk(SN, 'none')['no_git_tag_created']} of {rel(SN, 'none')['n']} Sonnet runs created a git tag")
ensure("security order: every no-skill run of that task on all three models",
       opt["rel-06-security"]["none"][0] == 0 and fails[("changelog_section_order",)] == opt["rel-06-security"]["none"][1]
       and all(sum(1 for r in MAIN if r["model"] == m and r["task"] == "rel-06-security" and r["condition"] == "none"
                   and not next(c for c in r["checks"] if c["name"] == "changelog_section_order")["ok"]) == 5 for m in (SN, H)))
rc = [r for r in MAIN if r["model"] == SN and r["task"] == "rel-05-rc" and r["condition"] == "none"]
rc_noentries = [r for r in rc if any(c["name"] == "changelog_release_heading" and not c["ok"] for c in r["checks"])]
rc_nofile = [r for r in rc_noentries if any(c["name"] == "release_file_exists" and not c["ok"] for c in r["checks"])]
need("rc 3 of 5, two without release file", f"(Sonnet, {len(rc_noentries)} of {len(rc)} runs, {WORDS[len(rc_nofile)]} of them also without the release file)")
hm = [r for r in MAIN if r["model"] == H and r["task"] == "rel-03-major" and r["condition"] == "none"]
need("haiku reworded 5 of 5", f"changelog entries reworded while being moved ({sum(any(c['name'] == 'changelog_entries_moved' and not c['ok'] for c in r['checks']) for r in hm)} of {len(hm)} runs of the major-release task)")
# chart: share of no-skill release runs failing each check
need("chart misses tag", f"{pc(ON['failed_checks']['no_git_tag_created'] / ON['n'])} of Opus 5.5 runs, {pc(chk(SN, 'none')['no_git_tag_created'] / 30)} of Sonnet 5.5 runs and {pc(chk(H, 'none')['no_git_tag_created'] / 30)} of Haiku 5.5 runs")
need("chart misses order", f"({pc(ON['failed_checks']['changelog_section_order'] / ON['n'])}, {pc(chk(SN, 'none')['changelog_section_order'] / 30)} and {pc(chk(H, 'none')['changelog_section_order'] / 30)})")
need("chart misses caption", f"{ON['n']} Opus 5.5 runs, {rel(SN, 'none')['n']} each for Sonnet 5.5 and Haiku 5.5")
# chart: pass rates
fam = lambda m, f, c: (OS["conditions"][c] if m == O else M[m]["families"][f][c])["pass_rate"]
need("chart pass release none", f"no skill, Opus {pc(fam(O, 'release', 'none'))}, Sonnet {pc(fam(SN, 'release', 'none'))}, Haiku {pc(fam(H, 'release', 'none'))}")
need("chart pass release compact", f"compact skill, Opus {pc(fam(O, 'release', 'compact'))}, Sonnet {pc(fam(SN, 'release', 'compact'))}, Haiku {pc(fam(H, 'release', 'compact'))}")
need("chart pass release comprehensive", f"comprehensive skill, Sonnet {pc(fam(SN, 'release', 'comprehensive'))}, Haiku {pc(fam(H, 'release', 'comprehensive'))}")
need("chart pass release selfgen", f"self-written skill, Sonnet {pc(fam(SN, 'release', 'selfgen'))}, Haiku {pc(fam(H, 'release', 'selfgen'))}")
need("chart pass migration", "Migration tasks, Sonnet and Haiku: " + "; ".join(
    f"{lab} {pc(fam(SN, 'migration', c))} and {pc(fam(H, 'migration', c))}" for c, lab in
    (("none", "no skill"), ("compact", "compact"), ("comprehensive", "comprehensive"), ("selfgen", "self-written"))))
need("chart caption opus 24 per bar", f"no skill and compact only, {ON['n']} runs per bar (6 tasks × 4 repeats, Claude Pro subscription). Sonnet 5.5 and Haiku 5.5: {rel(SN, 'none')['n']} runs per bar (6 tasks × 5 repeats, API)")
need("table caption", f"Sonnet and Haiku: {rel(SN, 'none')['n']} runs per task family and condition; \"All\" pools {cond(SN, 'none')['n']} runs")
need("table caption opus", f"*Opus 5.5: release tasks only, {ON['n']} runs per row (Claude Pro subscription)")
need("per-task caption", "out of 4 for Opus 5.5 (release tasks only, no skill and compact), out of 5 for Sonnet 5.5 and Haiku 5.5")
need("per-task heading", "Per-task passes (out of 5)")
need("per-task column heads", f"Opus: No skill (of {opt['rel-01-patch']['none'][1]}) Opus: Compact (of {opt['rel-01-patch']['compact'][1]})")
need("changelog 48 Opus runs", f"added {sub_n} Opus 5.5 release-task runs (Claude Pro subscription)")

# ---------------------------------------------------------------- cost table and text
for m in (SN, H):
    for c in CONDS:
        a = cond(m, c)
        row = (f"{CLABEL[c]} {cents(a['cost_mean'])} {cents(a['cost_per_pass'])} {kfmt(a['input_tokens_mean'])} "
               f"{n_(round(a['output_tokens_mean']))} {d1(a['turns_mean'])} {d1(a['wall_median'])}")
        need(f"cost table {NAME[m]} {c}", (f"{NAME[m]} " if c == "none" else "") + row)
need("cost caption 60 runs", f"API runs, means per run ({cond(SN, 'none')['n']} runs per row)")
need("chart cost sonnet", "Sonnet 5.5, mean cost per run: " + ", ".join(f"{lab} {cents(cond(SN, c)['cost_mean'])}" for c, lab in
     (("none", "no skill"), ("compact", "compact"), ("comprehensive", "comprehensive"), ("selfgen", "self-written")))
     + "; cost per passing run " + ", ".join(cents(cond(SN, c)["cost_per_pass"]) for c in CONDS))
need("chart cost haiku", "Haiku 5.5, mean cost per run: " + ", ".join(cents(cond(H, c)["cost_mean"]) for c in CONDS)
     + "; cost per passing run " + ", ".join(cents(cond(H, c)["cost_per_pass"]) for c in CONDS))
pc_s, pc_c, pc_h = pair(SN, "compact", "cost_all"), pair(SN, "comprehensive", "cost_all"), pair(H, "compact", "cost_all")
neg_ci = lambda c: sorted(-x for x in c)
need("sonnet -0.58 (0.40-0.75) 14%", f"cut Sonnet's cost by {cents(-pc_s['diff'])} cents a run (95% interval {cents(neg_ci(pc_s['ci'])[0])} to {cents(neg_ci(pc_s['ci'])[1])}), {pc(sn_cut)}")
need("sonnet output 1,012 vs 1,346", f"({n_(round(cond(SN, 'compact')['output_tokens_mean']))} tokens per run instead of {n_(round(cond(SN, 'none')['output_tokens_mean']))})")
need("opus 25% less per run (above)", f"({pc(op_cut)} less per run, above)")
need("haiku input/turns", f"using about {n_(round(cond(H, 'compact')['input_tokens_mean'] / 1000) * 1000)} input tokens per run instead of "
     f"{n_(round(cond(H, 'none')['input_tokens_mean'] / 10000) * 10000)} and {d1(cond(H, 'compact')['turns_mean'])} turns instead of {d1(cond(H, 'none')['turns_mean'])}")
need("haiku -0.15 (0.12-0.19) 31%", f"cost fell by {cents(-pc_h['diff'])} cents a run ({cents(neg_ci(pc_h['ci'])[0])} to {cents(neg_ci(pc_h['ci'])[1])}), {pc(h_cut)}")
need("comprehensive +0.31 (0.15-0.45) 7%", f"it cost {cents(pc_c['diff'])} cents more per run than no skill ({cents(pc_c['ci'][0])} to {cents(pc_c['ci'][1])}), about {pc(comp_up)}")
need("cost per pass 3.7 vs 6.4", f"on Sonnet, {cents(cond(SN, 'compact')['cost_per_pass'], 1)} cents with the compact skill against {cents(cond(SN, 'none')['cost_per_pass'], 1)} cents without one")
need("wall sonnet/haiku", f"Sonnet's median fell from {d1(cond(SN, 'none')['wall_median'])} to {d1(cond(SN, 'compact')['wall_median'])} seconds with the compact skill, "
     f"Haiku's from {d1(cond(H, 'none')['wall_median'])} to {d1(cond(H, 'compact')['wall_median'])}")
ensure("haiku comprehensive still cheaper than no skill", cond(H, "comprehensive")["cost_mean"] < cond(H, "none")["cost_mean"])

# ---------------------------------------------------------------- self-written skills
need("selfgen 0 of 30 both, against 10 and 5", f"{rel(SN, 'selfgen')['passed']} of {rel(SN, 'selfgen')['n']} on Sonnet and {rel(H, 'selfgen')['passed']} of {rel(H, 'selfgen')['n']} on Haiku, "
     f"against {rel(SN, 'none')['passed']} and {rel(H, 'none')['passed']} with no skill")
need("tagged in all 21 / all 30", f"they tagged in all {chk(SN, 'selfgen')['no_git_tag_created']} Sonnet runs that got as far as releasing and in all {chk(H, 'selfgen')['no_git_tag_created']} release runs on Haiku")
ensure("no-skill agents tagged in about half", all(abs(chk(m, "none")["no_git_tag_created"] / 30 - 0.5) < 0.05 for m in (SN, H)))
stall = [r for r in MAIN if r["model"] == SN and r["condition"] == "selfgen" and r["task"] in ("rel-03-major", "rel-04-changed")]
unchanged = [r for r in stall if next(c for c in r["checks"] if c["name"] == "version_pyproject")["detail"] == "1.4.2"]
need("sonnet stalled 9 of 10", f"Sonnet stopped to ask before changing anything in {len(unchanged)} of {len(stall)} runs")
ensure("21 + 9 stalled = 30 Sonnet selfgen release runs", chk(SN, "selfgen")["no_git_tag_created"] + len(unchanged) == rel(SN, "selfgen")["n"])
hmaj = [r for r in MAIN if r["model"] == H and r["condition"] == "selfgen" and r["task"] == "rel-03-major"]
h150 = [r for r in hmaj if next(c for c in r["checks"] if c["name"] == "version_pyproject")["detail"] == "1.5.0"]
need("haiku 1.5.0 in 5 of 5", f"so in {len(h150)} of {len(hmaj)} runs it released a Removed entry as 1.5.0 instead of 2.0.0")
sku = {m: [r for r in MAIN if r["model"] == m and r["condition"] == "selfgen" and r["task"] == "mig-05-sku"] for m in (SN, H)}
sku_ix = {m: sum(any(c["name"] == "index_naming_convention" and not c["ok"] for c in r["checks"]) for r in v) for m, v in sku.items()}
need("sku ix_ 5 of 5", f"both models named the unique SKU index ix_… in {sku_ix[SN]} of {len(sku[SN])} runs"); ensure("sku both models", sku_ix[SN] == sku_ix[H] == 5)
ensure("without a skill both passed the SKU task every run", SP["mig-05-sku"]["none"] == [5, 5] and HP["mig-05-sku"]["none"] == [5, 5])
sens = S["sensitivity_ignore_tag_rule"]
need("ignore tag rule", f"self-written skills passed {sens[SN]['selfgen']['release_passed']} of {sens[SN]['selfgen']['release_n']} release runs on Sonnet (no skill: {sens[SN]['none']['release_passed']}) "
     f"and {sens[H]['selfgen']['release_passed']} of {sens[H]['selfgen']['release_n']} on Haiku (no skill: {sens[H]['none']['release_passed']}), "
     f"while the compact skill still passed {sens[SN]['compact']['release_passed']} and {sens[H]['compact']['release_passed']}")

# ---------------------------------------------------------------- loading
skill_runs = [r for r in MAIN if r["model"] in (H, SN) and r["condition"] != "none"]
want = lambda r: "db-migrations" if r["family"] == "migration" else "release"
ensure("every skill run loaded the relevant skill", all(r["skill_calls"] and any(want(r) in s for s in r["skill_calls"]) for r in skill_runs))
o_skill = [r for r in SUBR if r["condition"] == "compact"]
ensure("every Opus skill run loaded the release skill", all(any("release" in s for s in r["skill_calls"]) for r in o_skill))
need("360 and 24 skill runs", f"In all {len(skill_runs)} Sonnet and Haiku skill runs and all {len(o_skill)} Opus skill runs")
need("trigger both models", f"Sonnet and Haiku both loaded the right kind of skill for {tr[H]['pos_triggered']} of {tr[H]['pos_n']} prompts that needed one and for none of the {tr[H]['neg_n']} that did not")
ensure("trigger Sonnet 20/20", tr[SN]["pos_triggered"] == 20 and tr[SN]["pos_n"] == 20)

# ---------------------------------------------------------------- limitations
need("p values", f"the permutation p-value for the compact skill is {po['p_perm']:.2f} on Opus (six release tasks) and {pair(SN, 'compact')['p_perm']:.2f} on Sonnet (all 12 tasks)")
improvable_o = [t for t, v in opt.items() if v["none"][0] < v["none"][1]]
improvable_s = [t for t, v in SP.items() if v["none"][0] < v["none"][1]]
need("opus 5 of 5 improvable, sonnet 4 of 4", f"Opus improved on {sum(opt[t]['compact'][0] > opt[t]['none'][0] for t in improvable_o)} of the {len(improvable_o)} tasks that could improve "
     f"and Sonnet on {sum(SP[t]['compact'][0] > SP[t]['none'][0] for t in improvable_s)} of {len(improvable_s)}")
need("haiku p 0.04", f"on Haiku it is {pair(H, 'compact')['p_perm']:.2f}")
ni = S["sensitivity_no_git_identity"][H]
need("no-identity batch", f"The no-identity batch ({sum(v['all']['n'] for v in ni.values())} Haiku runs) shows the same pattern for the curated skills "
     f"(no skill {ni['none']['all']['passed']} of {ni['none']['all']['n']}, compact {ni['compact']['all']['passed']}, comprehensive {ni['comprehensive']['all']['passed']}); "
     f"the self-written skills did better there ({ni['selfgen']['all']['passed']} of {ni['selfgen']['all']['n']})")
need("opus four repeats", "Opus ran the release tasks with no skill and the compact skill, four repeats each, on a Claude Pro subscription")
fab = [a for a in SUB["aborted"] if a["model"] == "claude-fable-5-1"]
ensure("Fable: one refused run, out of usage credits, 0 scored", len(fab) == 1 and "out of usage credits" in fab[0]["final_text"]
       and not any(r["model"] == "claude-fable-5-1" for r in SUBR))
need("Fable quote", "(\"You're out of usage credits\")")

# the reference solutions: every task passes, an untouched repository fails (same as `python -m pairedtest oracle skill_ab`)
import contextlib, io  # noqa: E402
sys.path.insert(0, str(ROOT))
from pairedtest.__main__ import oracle  # noqa: E402
from pairedtest.suite import load as load_suite  # noqa: E402
_suite = load_suite(ROOT / "skill_ab")
with contextlib.redirect_stdout(io.StringIO()):
    ensure("oracle: reference solutions pass, untouched repos fail", oracle(_suite) == 0)
need("reference solution all 12 tasks", f"A reference solution passes all {len(_suite.TASKS)} tasks and an untouched repository fails all of them")

# ---------------------------------------------------------------- CONTEXT: set-up, fixture and outside sources
# These numbers are not results. Each is listed with where it comes from; fixture facts are asserted.
FIX = ROOT / "fixture" / "tillroll"
nmig = len(list((FIX / "db" / "migrations").glob("0*.sql")))
CONTEXT = [
    ("date", "Published 8 October 2026Last verified 8 October 202617 min read"),
    ("date", "Published 8 October 2026 Last verified 8 October 2026 17 min read"),
    ("set-up", "the same 12 tasks in the same repository"),
    ("set-up", "ran the release tasks with no skill and with the short skill"),
    ("outside source: Agent Skills specification", "roughly 100 tokens each"),
    ("outside source: Agent Skills specification", "under 5,000 tokens and 500 lines"),
    ("outside source: SkillsBench", "SkillsBench: 87 tasks, 18 model and harness configurations, curated skills raising the average pass rate from 33.9% to 50.5%"),
    ("outside source: SkillsBench", "(+11.6 points)"),
    ("outside source: SkillsBench", "(Li et al., SkillsBench, 2026)"),
    ("outside source: SkillsBench", "(SkillsBench, appendix D.6.1)"),
    ("outside source: SkillsBench", "arXiv:2602.12670. arxiv.org/abs/2602.12670"),
    ("outside source: Wilson 1927", "Journal of the American Statistical Association 22 (1927). doi.org/10.1080/01621459.1927.10502953"),
    ("fixture", f"a SQLite schema with {WORDS[nmig]} migrations"),
    ("fixture", f"from the {WORDS[nmig]} existing migrations"),
    ("fixture", "Six migration tasks"), ("fixture", "Six release tasks"),
    ("fixture", "(\"Ticket OPS-437: orders can now carry a discount amount. Add a column for it\")"),
    ("fixture", "a three-line header"), ("fixture", "ix_orders__customer_id"), ("fixture", "SHA-256"),
    ("fixture", "release candidates are written 1.5.0rc1"), ("fixture", "a release/X.Y.Z.toml file"),
    ("fixture", "the history contains a v1.4.2 tag"), ("fixture", "The repository history contains a v1.4.2 tag"),
    ("fixture", "Two release rules"),
    ("set-up", "Pass rates carry 95% Wilson intervals"), ("set-up", "with a 95% bootstrap interval over tasks"),
    ("set-up", "with a 95% Wilson interval"), ("set-up", "Whiskers are 95% Wilson intervals"),
    ("set-up", "Python 3.13 and Node.js 22 were used"),
    ("set-up", "Fable 5.1"),
    ("fixture", "the file's SHA-256"),
    ("set-up", "Opus 5.5"), ("set-up", "Sonnet 5.5"), ("set-up", "Haiku 5.5"), ("set-up", "claude-opus-5-5"),
    ("set-up", "claude-sonnet-5-5"), ("set-up", "claude-haiku-5-5"),
    ("task ids", "mig-0"), ("task ids", "rel-0"),
    ("dates", "8 October 2026"),
    ("dates", "10 October 2026: added a link to the code and data on GitHub"),  # changelog line, once the repo link is live
    ("the SKILL.md template's numbered steps (template/SKILL.md)", "## Fast path 1. <The first concrete step"),
    ("the SKILL.md template's numbered steps (template/SKILL.md)", "2. <The next step"),
    ("the SKILL.md template's numbered steps (template/SKILL.md)", "3. <How to check the result"),
    ("set-up", "five repeats of the same task are not five independent samples"),
]
ensure("fixture: four migrations", nmig == 4)
ensure("fixture: tag v1.4.2 in the task set-up", "v1.4.2" in (ROOT / "skill_ab" / "tasks.py").read_text())
ensure("fixture: OPS-437 prompt", "Ticket OPS-437: orders can now carry a discount amount. Add a column for it" in (ROOT / "skill_ab" / "tasks.py").read_text())
ensure("fixture: rc format", "1.5.0rc1" in (ROOT / "skill_ab" / "tasks.py").read_text())

# ---------------------------------------------------------------- coverage of every digit in the note
covered = [False] * len(T)
for ph, ok in checks.values():
    if ok:
        for m_ in re.finditer(re.escape(ph), T):
            covered[m_.start():m_.end()] = [True] * (m_.end() - m_.start())
ctx_missing = []
for why, ph in CONTEXT:
    hits = list(re.finditer(re.escape(ph), T))
    for m_ in hits:
        covered[m_.start():m_.end()] = [True] * (m_.end() - m_.start())
unchecked = []
for m_ in re.finditer(r"(?<![\w])[+−-]?\d+(?:,\d{3})*(?:\.\d+)?%?", T):
    if not all(covered[m_.start():m_.end()]):
        unchecked.append(f"{m_.group(0)!r} in ...{T[max(0, m_.start() - 50):m_.end() + 30].strip()}...")

bad = [k for k, (ph, ok) in checks.items() if not ok]
print(f"phrases rendered from the data and found in the note: {len(checks) - len(bad)} / {len(checks)}")
for k in bad:
    print("  MISSING:", k, "->", repr(checks[k][0]))
print(f"data consistency checks: {len(problems)} failed" + (": " + "; ".join(problems) if problems else ""))
digits = len(re.findall(r"(?<![\w])[+−-]?\d+(?:,\d{3})*(?:\.\d+)?%?", T))
print(f"numbers written in digits in the note: {digits}; inside a checked phrase or listed context: {digits - len(unchecked)}; unchecked: {len(unchecked)}")
for u in unchecked:
    print("  UNCHECKED:", repr(u))
sys.exit(1 if bad or problems or unchecked else 0)

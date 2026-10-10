"""Article charts with Opus 5.5 and Sonnet 5.5 leading and Haiku 5.5 as a lighter, secondary series.
Reads results/summary.json (API runs) and results/subscription-summary.json (Opus, Claude Pro)."""
from __future__ import annotations

import json

import matplotlib.pyplot as plt

from charts import CHECK_LABEL, COND_LABEL, CONDS, INK, LINE, MUTED, NAVY, ROOT, TEAL, WHISKER, save, style

S = json.loads((ROOT / "results" / "summary.json").read_text())
SUB = json.loads((ROOT / "results" / "subscription-summary.json").read_text())
O, SN, H = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"
ORDER = [O, SN, H]
LABEL = {O: "Claude Opus 5.5", SN: "Claude Sonnet 5.5", H: "Claude Haiku 5.5"}
COLOUR = {O: NAVY, SN: TEAL, H: "#c3ccd4"}
FAM = {"release": "Release tasks (6)", "migration": "Migration tasks (6)"}


def cells(m: str, fam: str) -> dict:
    """Pass-rate cells per condition for one model and task family."""
    if m == O:
        return SUB["subscription"][O]["conditions"] if fam == "release" else {}
    return S["models"][m]["families"][fam]


def pass_rate() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 7.4), sharey=True, gridspec_kw={"width_ratios": [1, 1]})
    w = 0.27
    for ax, fam in zip(axes, ("release", "migration")):
        style(ax)
        for i, m in enumerate(ORDER):
            cs = cells(m, fam)
            for j, c in enumerate(CONDS):
                if c not in cs or not cs[c]["n"]:
                    continue
                d = cs[c]
                x = j + (i - 1) * w
                p = d["pass_rate"] * 100
                lo, hi = d["wilson"]
                ax.bar(x, p, w * 0.9, color=COLOUR[m], zorder=2)
                ax.errorbar([x], [p], yerr=[[p - lo * 100], [hi * 100 - p]], fmt="none", ecolor=WHISKER,
                            elinewidth=1.8, capsize=4, capthick=1.8, zorder=3, alpha=0.55 if m == H else 1)
                if p >= 30:  # at the foot of the bar, clear of the whiskers and of neighbouring labels
                    ax.text(x, 3, f"{p:.0f}%", ha="center", va="bottom", fontsize=10.5,
                            fontweight=800 if m != H else 600, color="white" if m != H else INK, zorder=4)
                else:
                    ax.text(x, hi * 100 + 2, f"{p:.0f}%", ha="center", va="bottom", fontsize=12 if m != H else 11,
                            fontweight=800 if m != H else 600, color=INK if m != H else MUTED, zorder=4)
        ax.set_xticks(range(len(CONDS)), [COND_LABEL[c] for c in CONDS], fontsize=13.5, fontweight=600)
        ax.set_ylim(0, 118)
        ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"], fontsize=13)
        ax.set_title(FAM[fam], loc="left", fontsize=18, fontweight=800, color=INK, pad=12)
    axes[0].text(0.99, 0.985, "Opus: no skill and compact only", transform=axes[0].transAxes, fontsize=12, color=MUTED, va="top", ha="right")
    axes[1].text(0.99, 0.985, "Opus: not run on migrations", transform=axes[1].transAxes, fontsize=12, color=MUTED, va="top", ha="right")
    fig.suptitle("Share of runs that followed every house rule", x=0.012, y=0.985, ha="left", fontsize=24, fontweight=800, color=INK)
    fig.text(0.012, 0.905, "Claude Code on 12 tasks in one repository, with and without an Agent Skill (SKILL.md)", fontsize=15, color=MUTED)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOUR[m]) for m in ORDER]
    fig.legend(handles, [LABEL[m] for m in ORDER], loc="upper left", bbox_to_anchor=(0.005, 0.875), frameon=False, fontsize=13.5, ncol=3)
    fig.text(0.012, 0.012, "Source: Veliora Engineering notes, 8 October 2026. Claude Code 2.1.293. Opus 5.5: 24 runs per bar (Claude Pro subscription).\n"
             "Sonnet 5.5 and Haiku 5.5: 30 runs per bar (API). Whiskers: 95% Wilson interval.", fontsize=10.5, color=MUTED, linespacing=1.4)
    fig.subplots_adjust(left=0.05, right=0.995, top=0.74, bottom=0.17, wspace=0.08)
    save(fig, "pass-rate-models")


def misses(top_n: int = 6) -> None:
    fails = {O: SUB["subscription"][O]["conditions"]["none"]["failed_checks"],
             SN: S["models"][SN]["checks"].get("none", {}), H: S["models"][H]["checks"].get("none", {})}
    n = {O: SUB["subscription"][O]["conditions"]["none"]["n"],
         SN: S["models"][SN]["families"]["release"]["none"]["n"], H: S["models"][H]["families"]["release"]["none"]["n"]}
    share = {m: {k: v / n[m] * 100 for k, v in fails[m].items()} for m in ORDER}
    total = {}
    for m in ORDER:
        for k, v in share[m].items():
            total[k] = total.get(k, 0) + v
    keys = [k for k, _ in sorted(total.items(), key=lambda kv: -kv[1])][:top_n][::-1]
    fig, ax = plt.subplots(figsize=(13, 0.78 * len(keys) + 2.4))
    for s_ in ("top", "right", "bottom"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="x", color=LINE)
    ax.set_axisbelow(True)
    h = 0.8 / len(ORDER)
    for i, m in enumerate(ORDER):
        ys = [y - (i - 1) * h for y in range(len(keys))]
        vals = [share[m].get(k, 0) for k in keys]
        ax.barh(ys, vals, h * 0.9, color=COLOUR[m], label=f"{LABEL[m]} ({n[m]} runs)", zorder=2)
        for y, v in zip(ys, vals):
            ax.text(v + 0.6, y, f"{v:.0f}%", va="center", fontsize=12 if m != H else 10.5,
                    fontweight=800 if m != H else 600, color=INK if m != H else MUTED)
    ax.set_yticks(range(len(keys)), [CHECK_LABEL.get(k, k) for k in keys], fontsize=14, fontweight=600)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, frameon=False, fontsize=12.5, loc="lower right")
    fig.suptitle("Release tasks without a skill: which rules were broken", x=0.012, y=0.985, ha="left", fontsize=22, fontweight=800, color=INK)
    fig.text(0.012, 0.012, "Share of no-skill release runs failing each check; a run can fail several. Opus 5.5 on a Claude Pro subscription; "
             "Sonnet 5.5 and Haiku 5.5 on the API.", fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.36, right=0.97, top=0.88, bottom=0.1)
    save(fig, "misses-models")


def cost() -> None:
    models = [SN, H]
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2))
    for ax, m in zip(axes, models):
        style(ax)
        conds = S["models"][m]["conditions"]
        vals = [conds[c]["cost_mean"] * 100 for c in CONDS]
        per_pass = [(conds[c]["cost_per_pass"] or 0) * 100 for c in CONDS]
        x = range(len(CONDS))
        ax.bar([i - 0.2 for i in x], vals, 0.38, color="#9aa5b1", label="Mean cost per run", zorder=2)
        ax.bar([i + 0.2 for i in x], per_pass, 0.38, color=COLOUR[m] if m != H else "#7f93a3", label="Cost per passing run", zorder=2)
        top = max(per_pass + vals)
        for i in x:
            ax.text(i - 0.2, vals[i] + top * 0.02, f"{vals[i]:.2f}", ha="center", va="bottom", fontsize=12.5, fontweight=700, color=MUTED)
            ax.text(i + 0.2, per_pass[i] + top * 0.02, f"{per_pass[i]:.2f}" if per_pass[i] else "no pass", ha="center",
                    va="bottom", fontsize=12.5, fontweight=800, color=INK)
        ax.set_ylim(0, top * 1.4)
        ax.set_xticks(list(x), [COND_LABEL[c] for c in CONDS], fontsize=13, fontweight=600)
        ax.set_title(f"{LABEL[m]}, US cents", loc="left", fontsize=17, fontweight=800, color=INK if m != H else MUTED, pad=10)
        ax.legend(frameon=False, fontsize=12.5, loc="upper left", ncol=2)
    fig.suptitle("What a run costs, and what a correct result costs", x=0.012, y=0.98, ha="left", fontsize=22, fontweight=800, color=INK)
    fig.text(0.012, 0.015, "API runs only: tokens reported by the API x Anthropic's published prices (8 Oct 2026). Cost per passing run = total cost / "
             "passing runs. Opus 5.5 ran on a subscription, so it is not shown.", fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.04, right=0.995, top=0.82, bottom=0.18, wspace=0.12)
    save(fig, "cost-models")


if __name__ == "__main__":
    pass_rate(); misses(); cost()
    print("written")

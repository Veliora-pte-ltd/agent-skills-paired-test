"""Render the article charts from results/summary.json (run analyse.py first).

    python charts.py            # writes charts/*.svg and charts/*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "charts"
for f in (OUT / "fonts").glob("*.ttf"):
    font_manager.fontManager.addfont(str(f))

NAVY, TEAL, TEAL_DARK, PAPER, INK, MUTED, LINE = "#081426", "#49c7ba", "#0f6f68", "#f5f3ee", "#0b1629", "#46566a", "#d6d2c8"
GREY = "#9aa5b1"
WHISKER = "#c0472a"
plt.rcParams.update({
    "font.family": "Figtree", "font.size": 15, "axes.edgecolor": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": MUTED, "svg.fonttype": "path", "figure.facecolor": PAPER,
    "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
})
CONDS = ["none", "compact", "comprehensive", "selfgen"]
COND_LABEL = {"none": "No skill", "compact": "Compact\nskill", "comprehensive": "Comprehensive\nskill",
              "selfgen": "Self-written\nskill"}
MODEL_LABEL = {"claude-haiku-5-5": "Claude Haiku 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5"}
MODEL_COLOUR = {"claude-haiku-5-5": TEAL, "claude-sonnet-5-5": NAVY}
FAMILY_LABEL = {"release": "Release tasks (6)", "migration": "Migration tasks (6)"}
SOURCE = "Source: Veliora Engineering notes, October 2026. Claude Code 2.1.293, 6 tasks x 5 repeats = 30 runs per bar. Whiskers: 95% Wilson interval."


def save(fig, name: str) -> None:
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / f"{name}.svg")
    fig.savefig(OUT / f"{name}.png", dpi=200)
    plt.close(fig)


def style(ax) -> None:
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(INK)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", color=LINE, linewidth=1)
    ax.set_axisbelow(True)


def pass_rate_chart(s: dict, size=(13, 7.2), name="pass-rate", title=True, families=("release", "migration")) -> None:
    models = [m for m in MODEL_LABEL if m in s["models"]]
    fig, axes = plt.subplots(1, len(families), figsize=size, sharey=True)
    if len(families) == 1:
        axes = [axes]
    w = 0.8 / len(models)
    for ax, fam in zip(axes, families):
        style(ax)
        for i, m in enumerate(models):
            fams = s["models"][m]["families"][fam]
            for j, c in enumerate(CONDS):
                if c not in fams:
                    continue
                d = fams[c]
                x = j + (i - (len(models) - 1) / 2) * w
                ax.bar(x, d["pass_rate"] * 100, w * 0.92, color=MODEL_COLOUR[m], zorder=2)
                lo, hi = d["wilson"]
                ax.errorbar([x], [d["pass_rate"] * 100], yerr=[[d["pass_rate"] * 100 - lo * 100], [hi * 100 - d["pass_rate"] * 100]],
                            fmt="none", ecolor=WHISKER, elinewidth=2, capsize=5, capthick=2, zorder=3)
                ax.text(x, hi * 100 + 2.0, f"{d['pass_rate']*100:.0f}%", ha="center", va="bottom",
                        fontsize=15, fontweight=800, color=INK, zorder=4)
        ax.set_xticks(range(len(CONDS)), [COND_LABEL[c] for c in CONDS], fontsize=14, fontweight=600)
        ax.set_ylim(0, 118)
        ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"], fontsize=13)
        ax.set_title(FAMILY_LABEL[fam], loc="left", fontsize=18, fontweight=800, color=INK, pad=12)
    handles = [plt.Rectangle((0, 0), 1, 1, color=MODEL_COLOUR[m]) for m in models]
    if title:
        fig.suptitle("Share of runs that followed every house rule", x=0.012, y=0.985, ha="left",
                     fontsize=24, fontweight=800, color=INK)
        fig.text(0.012, 0.905, "Claude Code on 12 tasks in one repository, with and without an Agent Skill (SKILL.md)",
                 fontsize=15, color=MUTED)
        fig.legend(handles, [MODEL_LABEL[m] for m in models], loc="upper right", bbox_to_anchor=(0.995, 0.99),
                   frameon=False, fontsize=14, ncol=len(models))
        fig.text(0.012, 0.015, SOURCE, fontsize=10.5, color=MUTED)
        fig.subplots_adjust(left=0.05, right=0.995, top=0.8, bottom=0.17, wspace=0.08)
    else:
        fig.legend(handles, [MODEL_LABEL[m] for m in models], loc="upper right", frameon=False, fontsize=14, ncol=2)
        fig.subplots_adjust(left=0.05, right=0.995, top=0.86, bottom=0.14, wspace=0.08)
    save(fig, name)


def cost_chart(s: dict) -> None:
    models = [m for m in MODEL_LABEL if m in s["models"]]
    fig, axes = plt.subplots(1, len(models), figsize=(13, 6.2))
    if len(models) == 1:
        axes = [axes]
    for ax, m in zip(axes, models):
        style(ax)
        conds = s["models"][m]["conditions"]
        vals = [conds[c]["cost_mean"] * 100 for c in CONDS]
        per_pass = [(conds[c]["cost_per_pass"] or 0) * 100 for c in CONDS]
        x = range(len(CONDS))
        ax.bar([i - 0.2 for i in x], vals, 0.38, color=GREY, label="Mean cost per run", zorder=2)
        ax.bar([i + 0.2 for i in x], per_pass, 0.38, color=MODEL_COLOUR[m], label="Cost per passing run", zorder=2)
        top = max(per_pass + vals)
        for i in x:
            ax.text(i - 0.2, vals[i] + top * 0.02, f"{vals[i]:.2f}", ha="center", va="bottom", fontsize=12.5, fontweight=700, color=MUTED)
            label = f"{per_pass[i]:.2f}" if per_pass[i] else "no pass"
            ax.text(i + 0.2, per_pass[i] + top * 0.02, label, ha="center", va="bottom", fontsize=12.5, fontweight=800, color=INK)
        ax.set_ylim(0, top * 1.4)
        ax.set_xticks(list(x), [COND_LABEL[c] for c in CONDS], fontsize=13, fontweight=600)
        ax.set_title(f"{MODEL_LABEL[m]}, US cents", loc="left", fontsize=17, fontweight=800, color=INK, pad=10)
        ax.legend(frameon=False, fontsize=12.5, loc="upper left", ncol=2)
    fig.suptitle("What a run costs, and what a correct result costs", x=0.012, y=0.98, ha="left", fontsize=22, fontweight=800, color=INK)
    fig.text(0.012, 0.015, "Cost = tokens reported by the API x Anthropic's published prices (8 Oct 2026). Cost per passing run = total cost / runs that passed.",
             fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.04, right=0.995, top=0.82, bottom=0.18, wspace=0.12)
    save(fig, "cost")


CHECK_LABEL = {
    "no_git_tag_created": "Created a git tag (CI owns tags)",
    "changelog_section_order": "Changelog sections out of house order",
    "changelog_entries_moved": "Changelog entries reworded or lost",
    "release_file_bump": "Wrong bump type in release file",
    "version_pyproject": "Wrong version number",
    "changelog_release_heading": "Wrong changelog heading",
    "release_file_migrations": "Wrong migration list in release file",
    "release_file_core_fields": "Release file fields wrong",
    "changelog_links": "Changelog compare links wrong",
    "release_file_exists": "No release file",
    "index_naming_convention": "Index not named ix_/ux_",
    "money_column_convention": "Money column not INTEGER *_minor",
    "schema_snapshot_regenerated": "schema.sql not regenerated",
    "manifest_entry": "Manifest entry or hash wrong",
    "header_lines": "Migration header wrong",
    "down_reverts_exactly": "Down migration does not revert",
    "changelog_unreleased_empty_on_top": "No empty Unreleased section",
    "version_init": "__version__ not updated",
    "changelog_history_untouched": "Older changelog entries edited",
    "intended_change": "Schema change not as asked",
    "created_at_convention": "created_at column not standard",
    "filename_format": "Migration file name wrong",
    "previous_release_files_untouched": "Older release files edited",
}


def misses_chart(s: dict, top_n: int = 6) -> None:
    models = [m for m in MODEL_LABEL if m in s["models"]]
    total = {}
    for m in models:
        for k, v in s["models"][m]["checks"].get("none", {}).items():
            total[k] = total.get(k, 0) + v
    keys = [k for k, _ in sorted(total.items(), key=lambda kv: -kv[1])][:top_n][::-1]
    fig, ax = plt.subplots(figsize=(13, 0.62 * len(keys) + 2.4))
    for s_ in ("top", "right", "bottom"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="x", color=LINE)
    ax.set_axisbelow(True)
    h = 0.8 / len(models)
    for i, m in enumerate(models):
        n = s["models"][m]["families"]["release"]["none"]["n"]
        vals = [s["models"][m]["checks"].get("none", {}).get(k, 0) / n * 100 for k in keys]
        ys = [y + (i - (len(models) - 1) / 2) * h for y in range(len(keys))]
        ax.barh(ys, vals, h * 0.9, color=MODEL_COLOUR[m], label=MODEL_LABEL[m], zorder=2)
        for y, v in zip(ys, vals):
            ax.text(v + 0.6, y, f"{v:.0f}%", va="center", fontsize=12.5, fontweight=800, color=INK)
    ax.set_yticks(range(len(keys)), [CHECK_LABEL.get(k, k) for k in keys], fontsize=14, fontweight=600)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.legend(frameon=False, fontsize=13, loc="lower right")
    fig.suptitle("Release tasks without a skill: which rules were broken", x=0.012, y=0.985, ha="left", fontsize=22, fontweight=800, color=INK)
    mig = "; ".join(f"{MODEL_LABEL[m]} {s['models'][m]['families']['migration']['none']['passed']}/"
                    f"{s['models'][m]['families']['migration']['none']['n']}" for m in models)
    fig.text(0.012, 0.012, "Share of no-skill release runs (30 per model) failing each check; a run can fail several. "
             f"No-skill migration runs passed: {mig}.",
             fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.36, right=0.97, top=0.86, bottom=0.1)
    save(fig, "misses")


def main() -> None:
    s = json.loads((ROOT / "results" / "summary.json").read_text())
    pass_rate_chart(s)
    pass_rate_chart(s, size=(7.2, 9.0), name="pass-rate-releases-portrait", title=False, families=("release",))
    cost_chart(s)
    misses_chart(s)
    print("charts written to", OUT)


if __name__ == "__main__":
    main()

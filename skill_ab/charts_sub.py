"""Chart for the subscription follow-up: release tasks, no skill vs compact skill, by model."""
from __future__ import annotations

import json

import matplotlib.pyplot as plt

from charts import GREY, INK, MUTED, NAVY, ROOT, TEAL, WHISKER, save, style

S = json.loads((ROOT / "results" / "subscription-summary.json").read_text())
ROWS = [("Claude Haiku 5.5", S["main_release"]["claude-haiku-5-5"], "API"),
        ("Claude Sonnet 5.5", S["main_release"]["claude-sonnet-5-5"], "API"),
        ("Claude Opus 5.5", S["subscription"]["claude-opus-5-5"], "Pro plan")]
COLOUR = {"none": GREY, "compact": TEAL}
LABEL = {"none": "No skill", "compact": "Compact skill"}


def main() -> None:
    fig, ax = plt.subplots(figsize=(13, 7.2))
    style(ax)
    w = 0.36
    for i, (name, d, src) in enumerate(ROWS):
        for j, c in enumerate(("none", "compact")):
            x = d["conditions"][c]
            p, (lo, hi) = x["pass_rate"] * 100, x["wilson"]
            xx = i + (j - 0.5) * w
            ax.bar(xx, p, w * 0.92, color=COLOUR[c], zorder=2)
            ax.errorbar([xx], [p], yerr=[[p - lo * 100], [hi * 100 - p]], fmt="none", ecolor=WHISKER,
                        elinewidth=2, capsize=5, capthick=2, zorder=3)
            ax.text(xx, hi * 100 + 2, f"{p:.0f}%", ha="center", va="bottom", fontsize=15, fontweight=800, color=INK)
            ax.text(xx, 2, f"{x['passed']}/{x['n']}", ha="center", va="bottom", fontsize=12, fontweight=700,
                    color="white" if c == "compact" else INK, zorder=4)
    ax.set_xticks(range(len(ROWS)), [f"{n}\n({s})" for n, _, s in ROWS], fontsize=14, fontweight=600)
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"], fontsize=13)
    fig.suptitle("Release tasks: runs that followed every house rule", x=0.012, y=0.985, ha="left",
                 fontsize=24, fontweight=800, color=INK)
    fig.text(0.012, 0.905, "Claude Code, 6 release tasks, with and without the compact skill", fontsize=15, color=MUTED)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOUR[c]) for c in ("none", "compact")]
    fig.legend(handles, [LABEL[c] for c in ("none", "compact")], loc="upper right", bbox_to_anchor=(0.995, 0.99),
               frameon=False, fontsize=14, ncol=2)
    fig.text(0.012, 0.015, "Source: Veliora Engineering notes, 8 October 2026. Claude Code 2.1.293. Haiku and Sonnet: 30 runs "
             "per bar (API). Opus: 24 runs per bar (Claude Pro subscription). Whiskers: 95% Wilson interval.",
             fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.995, top=0.8, bottom=0.17)
    save(fig, "release-by-model")


if __name__ == "__main__":
    main()

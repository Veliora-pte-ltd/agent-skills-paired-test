"""Published Anthropic API prices in US$ per million tokens, as read on 8 October 2026
(https://platform.claude.com/docs/en/about-claude/pricing). Prices change: check them before you
rely on cost figures, or pass your own table with --prices prices.json:

    {"claude-sonnet-5-5": [2.00, 2.50, 0.10, 10.00]}      # input, 5-min cache write, cache read, output

A model with no entry falls back to Claude Code's own total_cost_usd, which is a client-side
estimate, and the record says so in "cost_source".
"""
from __future__ import annotations

import json
from pathlib import Path

PRICES = {
    # model: (input, cache_write_5m, cache_read, output)
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-sonnet-5": (2.00, 2.50, 0.20, 10.00),
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-haiku-4-5": (1.00, 1.25, 0.10, 5.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}
LONG_PROMPT = {"claude-haiku-5-5": (100_000, (0.50, 0.625, 0.05, 2.50))}  # higher tier above this prompt size


def load(path: str | Path | None) -> dict:
    table = dict(PRICES)
    if path:
        table.update({k: tuple(v) for k, v in json.loads(Path(path).read_text()).items()})
    return table


def price_key(model: str, table: dict) -> str | None:
    for k in sorted(table, key=len, reverse=True):
        if model.startswith(k):
            return k
    return None


def call_cost(model: str, inp: int, cache_write: int, cache_read: int, out: int,
              max_prompt: int = 0, table: dict | None = None) -> float | None:
    """Cost of the token counts at list price, or None if the model has no price."""
    table = PRICES if table is None else table
    k = price_key(model, table)
    if k is None:
        return None
    p = table[k]
    if k in LONG_PROMPT and max_prompt > LONG_PROMPT[k][0]:
        p = LONG_PROMPT[k][1]
    return (inp * p[0] + cache_write * p[1] + cache_read * p[2] + out * p[3]) / 1e6

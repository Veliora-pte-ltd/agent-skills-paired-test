"""Published Anthropic API prices in US$ per million tokens.

Source: https://platform.claude.com/docs/en/about-claude/pricing (read 8 October 2026).
5-minute cache writes are 1.25x the input price; cache reads are listed per model.
Claude Haiku 5.5 has a higher tier for prompts over 100,000 tokens.
"""
from __future__ import annotations

PRICES = {
    # model: (input, cache_write_5m, cache_read, output)
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-sonnet-5": (2.00, 2.50, 0.20, 10.00),
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-haiku-4-5": (1.00, 1.25, 0.10, 5.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}
HAIKU55_LONG = (0.50, 0.625, 0.05, 2.50)  # prompts over 100k tokens


def _key(model: str) -> str:
    for k in sorted(PRICES, key=len, reverse=True):
        if model.startswith(k):
            return k
    raise KeyError(f"no price for model {model!r}; add it before running")


def call_cost(model: str, inp: int, cache_write: int, cache_read: int, out: int, long_prompt: bool = False) -> float:
    """Cost of the given token counts. `long_prompt` selects Haiku 5.5's >100k-token tier
    (applied to the whole run if any single call exceeded 100k tokens, which over-estimates)."""
    k = _key(model)
    p = PRICES[k]
    if k == "claude-haiku-5-5" and long_prompt:
        p = HAIKU55_LONG
    return (inp * p[0] + cache_write * p[1] + cache_read * p[2] + out * p[3]) / 1e6


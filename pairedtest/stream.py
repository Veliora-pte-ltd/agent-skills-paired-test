"""Read Claude Code's `--output-format stream-json` output: usage, cost, tools, skill loads, and
whether a run hit a usage limit or an auth problem. Logic taken from skill_ab/run.py and run_sub.py."""
from __future__ import annotations

import json
import re

from . import pricing

LIMIT = re.compile(r"usage limit|rate.?limit|hit your limit|limit reached|limit will reset|resets? at|quota|"
                   r"too many requests|out of usage credits|\b429\b", re.I)
AUTH = re.compile(r"not logged in|/login|auth(entication)?[_ ]?(error|failed)|oauth|invalid (api key|token|bearer)|"
                  r"token (has )?expired|unauthori[sz]ed|forbidden|\b401\b|\b403\b|credit balance", re.I)
# Account-identifying fields that may appear in stream events; replaced before anything is saved.
PRIVATE_KEYS = re.compile(r"(email|account|org|user_?id|subscription|PaymentMethod|PurchaseCredits|unifiedWindows)", re.I)


def events(lines: list[str]):
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            yield ev


def scrub(obj):
    """Replace the values of account-like keys with "[removed]", recursively."""
    if isinstance(obj, dict):
        return {k: ("[removed]" if PRIVATE_KEYS.search(k) else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def parse_stream(lines: list[str], prices: dict | None = None, skill_names: tuple = ()) -> dict:
    """Summarise one run. Totals come from the result event's modelUsage (per-message output
    counts in the stream are partial). Cost = tokens x list price; if a model has no price, Claude
    Code's total_cost_usd is used and cost_source says "cli_estimate"."""
    msgs, tools, result, init = {}, [], None, None
    for ev in events(lines):
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            init = ev
        elif t == "assistant":
            m = ev.get("message") or {}
            if ev.get("parent_tool_use_id") is None and "id" in m:
                msgs[m["id"]] = m  # the same id repeats per content block; keep the last
            for b in m.get("content", []) or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools.append({"name": b.get("name"), "input": b.get("input", {}) or {}})
        elif t == "result":
            result = ev
    result = result or {}
    max_prompt = 0
    for m in msgs.values():
        u = m.get("usage", {}) or {}
        max_prompt = max(max_prompt, u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                         + u.get("cache_read_input_tokens", 0))
    usage = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    cost, source = 0.0, "list_price"
    for model, mu in (result.get("modelUsage") or {}).items():
        i, cw, cr, o = (mu.get("inputTokens", 0), mu.get("cacheCreationInputTokens", 0),
                        mu.get("cacheReadInputTokens", 0), mu.get("outputTokens", 0))
        usage["input"] += i; usage["cache_write"] += cw; usage["cache_read"] += cr; usage["output"] += o
        c = pricing.call_cost(model, i, cw, cr, o, max_prompt, prices)
        if c is None:
            c, source = float(mu.get("costUSD", 0.0)), "cli_estimate"
        cost += c
    if not result.get("modelUsage") and result.get("total_cost_usd") is not None:
        cost, source = float(result["total_cost_usd"]), "cli_estimate"
    skill_calls = []
    for tl in tools:
        inp = json.dumps(tl["input"])
        if tl["name"] == "Skill":
            skill_calls.append(tl["input"].get("skill") or tl["input"].get("command") or inp[:80])
        elif "SKILL.md" in inp and tl["name"] in ("Read", "Bash", "Grep", "Glob"):
            skill_calls.append("read:" + inp[:120])
    return {
        "api_calls": len(msgs), "usage": usage, "cost_usd": cost, "cost_source": source,
        "max_prompt_tokens": max_prompt, "cli_cost_usd": result.get("total_cost_usd"),
        "num_turns": result.get("num_turns"), "duration_ms": result.get("duration_ms"),
        "is_error": result.get("is_error"), "result_subtype": result.get("subtype"),
        "tool_calls": len(tools), "tool_names": [t["name"] for t in tools], "skill_calls": skill_calls,
        "skills_listed": list((init or {}).get("skills", [])) if init else None,
        "api_key_source": (init or {}).get("apiKeySource"),
        "claude_code_version": (init or {}).get("claude_code_version"),
        "final_text": (result.get("result") or "")[:2000],
    }


def classify(lines: list[str], stderr: str, rc: int, auth: str = "api") -> str | None:
    """'limit', 'auth' or 'api_error' if the run should stop the batch; None for an ordinary
    (passed or failed) run. In subscription mode, any API-key source counts as an auth fault."""
    result, init, rl = None, None, []
    for ev in events(lines):
        t = str(ev.get("type", ""))
        if t == "result":
            result = ev
        elif t == "system" and ev.get("subtype") == "init":
            init = ev
        if "rate_limit" in t:
            rl.append(ev.get("rate_limit_info", ev))
    src = str((init or {}).get("apiKeySource") or "")
    if auth == "subscription" and ("API_KEY" in src.upper() or "apikeyhelper" in src.lower()):
        return "auth"
    if any(str(i.get("status", "")).lower() in ("rejected", "blocked", "exceeded") for i in rl):
        return "limit"
    status = (result or {}).get("api_error_status")
    if status == 429:
        return "limit"
    if status in (401, 403):
        return "auth"
    if stderr == "timeout":
        return None  # harness timeout: scored as a failed run
    if result is not None and result.get("subtype") == "error_max_budget_usd":
        return None  # per-run cap hit: an ordinary failed run
    text = " ".join([str((result or {}).get("result") or ""), stderr[-3000:]])
    errored = result is None or bool(result.get("is_error")) or status is not None or rc != 0
    if errored:
        if LIMIT.search(text):
            return "limit"
        if AUTH.search(text):
            return "auth"
        if status is not None or result is None:
            return "api_error"
    return None

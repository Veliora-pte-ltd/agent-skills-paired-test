#!/usr/bin/env python3
"""A stand-in for the `claude` binary, used by the tests so no model is called and nothing is spent.

It emits Claude Code-style stream-json. With the template suite's `adr` skill installed it follows
the skill; without it, it copies the existing ADRs (and so writes "Accepted", the wrong status).
FAKE_CLAUDE_MODE=leak prints the API key; FAKE_CLAUDE_MODE=limit simulates a usage limit.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
model = args[args.index("--model") + 1] if "--model" in args else "unknown"
mode = os.environ.get("FAKE_CLAUDE_MODE", "")
key_src = "ANTHROPIC_API_KEY" if os.environ.get("ANTHROPIC_API_KEY") else "none"
skills = sorted(p.name for p in Path(".claude/skills").glob("*")) if Path(".claude/skills").exists() else []
emit = lambda ev: print(json.dumps(ev), flush=True)
emit({"type": "system", "subtype": "init", "apiKeySource": key_src, "claude_code_version": "fake",
      "skills": skills, "account": {"email": "someone@example.org"}, "cwd": os.getcwd()})
if mode == "limit":
    emit({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "errorCode": "credits_required"}})
    emit({"type": "result", "subtype": "success", "is_error": True, "result": "You're out of usage credits.",
          "num_turns": 1, "total_cost_usd": 0, "modelUsage": {}})
    sys.exit(1)
content = []
if "adr" in skills:
    content.append({"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "adr"}})
emit({"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m1", "content": content,
      "usage": {"input_tokens": 5, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 900}}})
adr = Path("docs/adr")
n = max(int(p.name[:4]) for p in adr.glob("[0-9]*.md")) + 1
title = "Move to Postgres for the hosted version" if "Postgres" in args[args.index("-p") + 1] else "Send emails through a background job queue"
slug = title.lower().replace(" ", "-")
status = "Proposed" if "adr" in skills else "Accepted"
(adr / f"{n:04d}-{slug}.md").write_text(
    f"# {n}. {title}\n\nDate: {dt.date.today().isoformat()}\nStatus: {status}\n\n"
    "## Context\n\nx\n\n## Decision\n\nx\n\n## Consequences\n\nx\n")
with open(adr / "README.md", "a") as fh:
    fh.write(f"| [{n:04d}]({n:04d}-{slug}.md) | {title} | {status} |\n")
out = 200 if skills else 300
text = "Done." + (f" key={os.environ.get('ANTHROPIC_API_KEY')}" if mode == "leak" else "")
emit({"type": "result", "subtype": "success", "is_error": False, "result": text, "num_turns": 3, "duration_ms": 10,
      "total_cost_usd": 0.0123,
      "modelUsage": {model: {"inputTokens": 5, "cacheCreationInputTokens": 100, "cacheReadInputTokens": 900, "outputTokens": out}}})

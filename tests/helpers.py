from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FAKE = Path(__file__).resolve().parent / "fake_claude.py"


def fake_claude(tmp: Path, mode: str = "") -> str:
    """A wrapper script that runs fake_claude.py in the given mode (the runner gives the child a clean env)."""
    w = tmp / f"claude-{mode or 'normal'}"
    w.write_text(f'#!/bin/sh\nFAKE_CLAUDE_MODE={mode} exec "{sys.executable}" "{FAKE}" "$@"\n')
    w.chmod(w.stat().st_mode | stat.S_IEXEC)
    return str(w)

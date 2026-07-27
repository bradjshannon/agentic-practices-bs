#!/usr/bin/env python3
"""EXAMPLE TRIGGER — a SessionStart hook that surfaces overdue freshness entries at turn 0.

    *** THIS IS AN EXAMPLE TO ADAPT, NOT A THING TO INSTALL AS-IS. ***

The sweeper (`../check_freshness.py`) is a perfectly deterministic instrument with one fatal
property: **somebody has to run it.** That is the Voluntary class — the weakest row of the
table in `mechanisms/README.md` — and it decays exactly the way that table predicts. The
registries this was written against held 19 entries, every one seeded on the same day, and
not one had been swept in the weeks since. Nobody defected; nobody remembered.

This file is one worked answer: move the control up a class by making the sweep happen
*without anyone deciding to sweep*. Read `README.md` in the parent directory for why this
particular class was chosen over a pre-commit gate or a scheduled task, and for the honest
list of what it does not catch.

WHAT IT DOES
------------
Runs on Claude Code's `SessionStart` event. For each registry it is told about, it runs the
sweeper and — only if something is DUE, OVERDUE, ALWAYS or MALFORMED — injects a short block
into the session's opening context. When everything is clean it prints nothing at all, so the
steady-state cost is zero tokens. An agent that has never read this repo still sees the
overdue list, because it arrives as context rather than as a rule to remember.

CONFIGURATION (environment, so nothing here is machine-specific)
----------------------------------------------------------------
    FRESHNESS_REGISTRIES  os.pathsep-separated list of registry files to sweep.
                          Unset -> ./freshness.md if it exists, else nothing.
    FRESHNESS_CHECK       path to check_freshness.py.
                          Unset -> ~/.claude/skills/freshness-check/check_freshness.py
    FRESHNESS_MAX_LINES   cap on injected lines per registry (default 40), so a badly
                          neglected registry cannot eat the context window it is
                          interrupting.

INSTALL (adapt the paths; see the parent README before you do)
--------------------------------------------------------------
Copy this file somewhere stable, then add to your Claude Code settings JSON:

    "hooks": {
      "SessionStart": [
        {"hooks": [{"type": "command",
                    "command": "python /path/to/session_start_freshness.py"}]}
      ]
    }

Verify it can actually fire before trusting it: run it by hand with a registry that is
definitely overdue --

    FRESHNESS_REGISTRIES=/path/to/freshness.md python session_start_freshness.py

-- and confirm you get JSON with a non-empty `additionalContext`. A hook that has never been
seen to fire is indistinguishable from one that is wired wrong.

FAILURE POSTURE
---------------
Every failure path here exits 0 and prints nothing. A hook that can break session startup
is a hook that gets removed after the first bad morning, and then it enforces nothing at
all. The cost of that choice is that this control is silently absent when the sweeper is
missing or Python cannot import PyYAML -- which is named in the parent README's holes list
rather than hidden here.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

DEFAULT_CHECKER = pathlib.Path.home() / ".claude" / "skills" / "freshness-check" / "check_freshness.py"
INTERESTING = ("[DUE", "[OVERDUE", "[ALWAYS", "[MALFORMED")


def _registries() -> list[pathlib.Path]:
    raw = os.environ.get("FRESHNESS_REGISTRIES", "").strip()
    if raw:
        return [pathlib.Path(p) for p in raw.split(os.pathsep) if p.strip()]
    local = pathlib.Path.cwd() / "freshness.md"
    return [local] if local.exists() else []


def _sweep(checker: pathlib.Path, registry: pathlib.Path, max_lines: int) -> str:
    """Return the report for one registry, or '' if it is clean / unreadable."""
    try:
        out = subprocess.run(
            [sys.executable, str(checker), str(registry)],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return ""  # see FAILURE POSTURE
    # Exit 0 means nothing needs attention. Exit 2 is a usage/parse error -- worth seeing,
    # because a registry that stopped parsing has silently stopped protecting anything.
    if out.returncode == 0:
        return ""
    if out.returncode == 2:
        return f"{registry}: registry did not parse -- it is currently watching nothing.\n"

    lines = [ln.rstrip() for ln in out.stdout.splitlines()]
    keep: list[str] = []
    emitting = False
    for ln in lines:
        if any(ln.lstrip().startswith(tag) for tag in INTERESTING):
            emitting = True
        elif ln.strip() == "":
            emitting = False
        if emitting:
            keep.append(ln)
    if not keep:
        return ""
    truncated = len(keep) > max_lines
    body = "\n".join(keep[:max_lines])
    if truncated:
        body += f"\n... ({len(keep) - max_lines} more lines; run the sweeper directly)"
    return f"{registry}\n{body}\n"


def main() -> int:
    # SessionStart delivers a JSON payload on stdin. Nothing here needs it, but it must be
    # drained: a hook that leaves stdin unread can wedge the caller on a full pipe.
    try:
        sys.stdin.read()
    except Exception:
        pass

    checker = pathlib.Path(os.environ.get("FRESHNESS_CHECK") or DEFAULT_CHECKER)
    if not checker.exists():
        return 0
    try:
        max_lines = int(os.environ.get("FRESHNESS_MAX_LINES", "40"))
    except ValueError:
        max_lines = 40

    reports = [r for r in (_sweep(checker, reg, max_lines)
                           for reg in _registries() if reg.exists()) if r]
    if not reports:
        return 0

    context = (
        "Freshness registry: entries are past their re-verification cadence.\n\n"
        + "\n".join(reports)
        + "\nThese are recorded claims that other documents rely on, and their recorded age "
          "now exceeds the cadence their author set. Re-verify each one via its `how_to_check` "
          "and either bump `last_checked` or fix the document named in `location`. If a claim "
          "has stopped being load-bearing, delete the entry -- a registry that only accretes "
          "becomes the stale thing it was built to catch.\n"
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

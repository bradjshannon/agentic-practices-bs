#!/usr/bin/env python3
"""PreToolUse(Bash) guard -- a subagent backgrounding a step will NOT be resumed by it.

WHY THIS EXISTS (queued 2026-08-03, built 2026-08-04, the operator: "note this hook as a todo item.
easy to sub out, probably." -- then "Do it").

A subagent's turn ending IS its return to the parent; there is no mechanism that wakes a
subagent when its own backgrounded command completes (see
agentic-practices-bs/lessons/subagent-must-not-background-and-wait-2026-07-18.md). A subagent
that runs a slow step with `run_in_background: true` and then ends its turn expecting to be
resumed by the completion has, from the parent's point of view, simply died mid-task -- no
report, no commit, nothing. Motivating instance: the conductor_core extraction agent backgrounded
its own test suite, ended its turn, and never reported; a firmware agent hit the same shape
23:45-04:44 the same week (repo_doc_guard.py-adjacent lesson, same brief section).

Backgrounding itself is NOT the mistake -- a subagent that backgrounds a slow step and then
POLLS IT TO COMPLETION BEFORE ENDING ITS TURN is doing exactly the right thing (this is what
lets a long build run without the subagent going silent-and-blocking for ten minutes). The
mistake is backgrounding and then ending the turn on the assumption of being woken up. This
hook cannot see the future (whether the subagent's NEXT action will be a poll or a turn-end),
so it does the only honest thing: remind, once per actor per session, at the moment of
backgrounding -- cheap, not a hard gate, easily overridden.

DESIGN CONTRACT (same shape as repo_doc_guard.py / lying_command_guard.py):
  - FAIL-OPEN on any script error, malformed payload, or missing state dir: never block a
    background dispatch because this guard broke.
  - Fires ONLY when BOTH hold: `tool_input.run_in_background` is true, AND the actor is a
    delegated agent (`agent_id` present in the payload -- same signal repo_doc_guard.py uses;
    the top-level conductor backgrounding its own pacer/build is a completely different case
    with a real wake path and must never be interrupted here).
  - BLOCKS ONCE per (session_id, agent_id) -- a state file records that this actor has already
    been reminded; every call after the first for that actor is allowed through silently. A
    guard that fires on every single backgrounded command in a long tool-heavy subagent run
    would train the actor to stop reading it, the same failure lying_command_guard.py's own
    docstring warns about.
  - Escape hatch, same token shape as lying_command_guard.py: `# bg:ok` anywhere in the command
    string skips the reminder for that call without consuming the once-per-actor budget (a
    subagent that already knows the rule and is intentionally polling can silence it inline).

Reads hook input as JSON on stdin:
  {tool_name, tool_input:{command, run_in_background}, agent_id, session_id, transcript_path, ...}

INSTALL, PreToolUse, matcher "Bash":
  {"matcher": "Bash", "hooks": [{"type": "command", "timeout": 10,
    "command": "py -3 -c \\"import runpy,os;runpy.run_path(os.path.expanduser('~/.claude/hooks/subagent_background_wait_guard.py'),run_name='__main__')\\""}]}
"""
from __future__ import annotations

import json
import os
import re
import sys

OVERRIDE = re.compile(r"#\s*bg:\s*ok\b", re.I)


def _state_dir():
    # Env override for tests -- same reasoning as estimate_tracker.py's _state_dir(): a
    # module-level constant can't be patched after runpy.run_path() returns a copy of the
    # module's globals, so tests need a real env-var seam instead.
    return os.environ.get("SUBAGENT_BG_GUARD_STATE_DIR") or os.path.expanduser("~/.claude/state")


def _warned_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    return os.path.join(_state_dir(), f"subagent-bg-warned-{safe}.json")


def _load_warned(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return set(data) if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def _save_warned(path, warned):
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sorted(warned), fh)
        os.replace(tmp, path)
    except OSError:
        pass


def _log(trigger, agent_id=None):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("subagent_background_wait_guard", trigger=str(trigger)[:120],
                        extra={"agent_id": agent_id})
    except Exception:
        pass


REASON = (
    "Reminder (once per subagent per session): backgrounding this command does NOT mean you "
    "will be resumed when it finishes. A subagent's turn ending IS its return to the parent -- "
    "there is no mechanism that wakes a subagent on a background completion the way the "
    "top-level conductor gets woken. If your NEXT action is to end this turn expecting to be "
    "resumed, that will not happen and this work will silently vanish, exactly like the "
    "conductor_core extraction agent that backgrounded its own test suite and was never heard "
    "from again.\n\n"
    "This is fine if you POLL the command to completion yourself before ending your turn (check "
    "its output, wait, retry) -- backgrounding a slow step so you are not blocked-and-silent for "
    "ten minutes is the right move. It is only wrong to background-and-stop.\n\n"
    "This will not fire again for you this session. To silence it for this one call instead, "
    "add `# bg:ok` to the command."
)


def allow():
    sys.exit(0)


def warn_once(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return allow()

    # `_log()` is reached from deep in the logic without the payload, so bind it here. Without
    # this every fire records `session: null` and hook_rollup.py can classify none of them.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.bind(payload)
    except Exception:
        pass

    try:
        if payload.get("tool_name") != "Bash":
            return allow()
        tool_input = payload.get("tool_input") or {}
        if not tool_input.get("run_in_background"):
            return allow()
        agent_id = payload.get("agent_id")
        if not agent_id:
            # The top-level conductor backgrounding its own pacer/build has a real wake path
            # (the harness re-invokes it on completion). This guard is only for a DELEGATED
            # agent, which has no such path -- see the module docstring.
            return allow()

        cmd = tool_input.get("command") or ""
        if OVERRIDE.search(cmd):
            _log("overridden (# bg:ok)", agent_id=agent_id)
            return allow()

        session_id = payload.get("session_id")
        path = _warned_path(session_id)
        warned = _load_warned(path)
        if agent_id in warned:
            return allow()  # already reminded this actor this session

        warned.add(agent_id)
        _save_warned(path, warned)
        _log("first background dispatch this session", agent_id=agent_id)
        warn_once(REASON)
    except SystemExit:
        raise
    except Exception:
        return allow()  # FAIL-OPEN: never block a dispatch because this guard broke


if __name__ == "__main__":
    main()

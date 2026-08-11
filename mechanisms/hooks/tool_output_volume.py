#!/usr/bin/env python3
"""PostToolUse instrument — how much raw command output did I pull into MY OWN context?

REQUIREMENT FIRST (Brad, 2026-08-08): the consumer is a conductor deciding, per command, whether
to run it inline or hand it to a chore-runner. To make that decision it needs a number that does
not exist anywhere today: at turn end, how many characters of raw tool output it absorbed itself,
and which specific calls were the offenders. Without that number the "delegate voluminous output"
rule has no feedback loop, and it has measurably decayed -- 2 chore-runner dispatches against 154
for the busiest SME type. This file is the collection layer for that number. Nothing else.

WHY MEASUREMENT AND NOT A GUARD
A PreToolUse block on command SHAPE was considered and rejected. `git log --oneline -3` and
`pytest -q` match the same shapes as the calls that dump 30k, and a check with false positives
gets routed around -- taking its true positives with it. Volume is only knowable AFTER the call
returns, which is exactly what PostToolUse gives. So: never blocks, never rewrites, never
non-zero-exits on its own errors. Every path fails open; a crash here costs nothing.

WHAT IT RECORDS, one line per command call, via hook_log (no second log file):
  chars        -- length of the tool result text as delivered into context (stdout+stderr)
  cmd          -- first 120 chars of the command, as hook_log's `trigger`
  spooled      -- whether the harness truncated this result and wrote the full text to a file
  spooled_size -- the true pre-truncation size when spooled
  tool         -- "Bash" or "PowerShell"
NOT the result CONTENT. This log already carries command lines (which can contain secrets in
argv); adding result bodies would turn a metrics file into a data-exfiltration surface.

TRUNCATION IS RELIABLY DETECTABLE -- verified empirically, not assumed. Across 1135 real Bash
results in the last 6 transcripts of this project, the harness attaches `persistedOutputPath` and
`persistedOutputSize` to exactly the results it spooled (6 of 1135), and every result with stdout
at or near the ~30000 cap carried them. There is no in-band marker string to sniff for and none is
invented here: `spooled` is True iff those fields are present. `spooled_size` is the harness's own
count of what the command really produced, so the gap between `chars` and `spooled_size` is
visible rather than guessed at.

DELIBERATE DEVIATION FROM THE BRIEF: the brief said Bash. This also matches PowerShell, which is
the primary shell on this Windows box and produces identical result shapes. Measuring one and not
the other would leave a hole exactly where the volume is. `tool` is recorded per entry so the two
can be separated at analysis time.

INSTALL
  PostToolUse, matcher "Bash|PowerShell" (same command/timeout convention as estimate_tracker.py):

    {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "timeout": 10,
      "command": "py -3 -c \\"import runpy,os;runpy.run_path(os.path.expanduser('~/.claude/hooks/tool_output_volume.py'),run_name='__main__')\\""}]}
"""
from __future__ import annotations

import json
import os
import sys

MATCHED_TOOLS = ("Bash", "PowerShell")
CMD_CHARS = 120


def allow():
    sys.exit(0)


def result_chars(response) -> int:
    """Characters of tool result text delivered into context. Best-effort; never raises.

    Shape-tolerant on purpose: the Bash result is normally a dict with stdout/stderr, but a
    hook that only understands one shape silently records 0 forever if the shape ever changes,
    and a metric that reads 0 is worse than no metric.
    """
    if isinstance(response, str):
        return len(response)
    if not isinstance(response, dict):
        return 0
    n = 0
    seen = False
    for key in ("stdout", "stderr", "output", "content", "result"):
        val = response.get(key)
        if isinstance(val, str):
            n += len(val)
            seen = True
    if seen:
        return n
    try:
        return len(json.dumps(response))
    except (TypeError, ValueError):
        return 0


def spool_info(response):
    """(spooled, true_size_or_None).

    The harness truncates around 30k and writes the full text to a sidecar file, announcing it
    out-of-band with `persistedOutputPath` / `persistedOutputSize`. Those fields ARE the signal --
    see the module docstring for the measurement that established it. No content sniffing.
    """
    if not isinstance(response, dict):
        return False, None
    path = response.get("persistedOutputPath")
    size = response.get("persistedOutputSize")
    spooled = bool(path) or isinstance(size, int)
    return spooled, size if isinstance(size, int) else None


def handle_post(payload):
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    response = payload.get("tool_response")

    chars = result_chars(response)
    spooled, size = spool_info(response)
    cmd = tool_input.get("command")
    cmd = (cmd if isinstance(cmd, str) else "")[:CMD_CHARS]

    extra = {"chars": chars, "tool": tool, "spooled": spooled}
    if size is not None:
        extra["spooled_size"] = size
    # Whose context did this output land in? `session` is the TOP-LEVEL session id and is
    # identical for the conductor and every subagent under it, so without this field a fan-out's
    # volume is one undifferentiated stream. Absent for the top-level actor by design.
    agent_id = payload.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        extra["agent_id"] = agent_id

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import hook_log
    hook_log.record(
        "tool_output_volume",
        trigger=cmd,
        transcript_path=payload.get("transcript_path"),
        session=payload.get("session_id"),
        extra=extra,
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return allow()
    try:
        if (payload.get("tool_name") or "") not in MATCHED_TOOLS:
            return allow()
        if (payload.get("hook_event_name") or "") != "PostToolUse":
            return allow()
        handle_post(payload)
    except Exception:  # noqa: BLE001 -- fail-open is the contract. This is an instrument, not a
        # control; a bug here must never cost a tool call, a turn, or an exit code.
        pass
    return allow()


if __name__ == "__main__":
    main()

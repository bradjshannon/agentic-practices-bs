#!/usr/bin/env python3
"""PostToolUse instrument — how much raw tool output did I pull into MY OWN context?

REQUIREMENT FIRST (the operator, 2026-08-08): the consumer is a conductor deciding, per call, whether
to run it inline or hand it to a chore-runner. To make that decision it needs a number that does
not exist anywhere today: at turn end, how many characters of raw tool output it absorbed itself,
and which specific calls were the offenders. Without that number the "delegate voluminous output"
rule has no feedback loop, and it has measurably decayed.

    RE-DERIVED 2026-08-17 across all 92 transcripts of this project, deduping by tool_use id:
    26 myproject-chore-runner dispatches against 1,091 total Agent dispatches (2.4%); the busiest
    SME type is myproject-firmware at 296. The figure this docstring previously carried -- "2
    chore-runner dispatches against 154" -- was measured over a much smaller window and is
    superseded. The CONCLUSION is unchanged and got worse in absolute terms: the mechanism
    built to absorb voluminous output is reached for in 1 dispatch in 42.

WHY MEASUREMENT AND NOT A GUARD
A PreToolUse block on command SHAPE was considered and rejected. `git log --oneline -3` and
`pytest -q` match the same shapes as the calls that dump 30k, and a check with false positives
gets routed around -- taking its true positives with it. Volume is only knowable AFTER the call
returns, which is exactly what PostToolUse gives. So: never blocks, never rewrites, never
non-zero-exits on its own errors. Every path fails open; a crash here costs nothing.

WHAT IT RECORDS, one line per matched call, via hook_log (no second log file):
  chars        -- length of the tool result text as delivered into context
  trigger      -- first 120 chars of the call's IDENTITY (command / file / pattern / agent type)
  spooled      -- whether the harness truncated this result and wrote the full text to a file
  spooled_size -- the true pre-truncation size when spooled
  tool         -- the tool name
NOT the result CONTENT. This log already carries command lines (which can contain secrets in
argv); adding result bodies would turn a metrics file into a data-exfiltration surface.

TRUNCATION IS RELIABLY DETECTABLE -- verified empirically, not assumed. Across 1135 real Bash
results in the last 6 transcripts of this project, the harness attaches `persistedOutputPath` and
`persistedOutputSize` to exactly the results it spooled (6 of 1135), and every result with stdout
at or near the ~30000 cap carried them. There is no in-band marker string to sniff for and none is
invented here: `spooled` is True iff those fields are present. `spooled_size` is the harness's own
count of what the command really produced, so the gap between `chars` and `spooled_size` is
visible rather than guessed at.

DELIBERATE DEVIATION FROM THE ORIGINAL BRIEF: that brief said Bash. This also matches PowerShell,
which is the primary shell on this Windows box and produces identical result shapes. Measuring one
and not the other would leave a hole exactly where the volume is. `tool` is recorded per entry so
they can be separated at analysis time.

2026-08-17 -- EXTENDED BEYOND THE SHELLS, BECAUSE THE SHELLS WERE THE MINORITY
-----------------------------------------------------------------------------
This hook was wired PostToolUse on "Bash|PowerShell" and nothing else, so it measured the shells
and was blind to every other tool. `tools/context_intake.py` attributed context growth to the tool
call that caused it across 87 sessions / 30,990 billed messages / 36.2M result chars, ranking by
AMORTISED cost (a result's size times the number of billed messages that go on to re-read it):

    Read        50.6% of amortised intake, from  1,883 calls   <- ENTIRELY UNSEEN
    Bash        38.5% of amortised intake, from 19,012 calls   <- seen
    Agent        2.7%                                          <- unseen
    PowerShell   1.5%                                          <- seen
    Grep/other  ~6.7%                                          <- unseen

i.e. the wired matcher could see 40.0% of amortised intake and was blind to 60.0%, and the single
biggest contributor was the one tool it never matched. Read makes 6.8% of the calls and carries
half the amortised cost: its median result is 1,821 chars against Bash's 311, and its p90 is
33,099 against Bash's 1,780. A "which calls were the offenders" number computed from the shells
only is not merely incomplete -- it points at the wrong tool.

So MATCHED_TOOLS now covers Read, Grep, Glob, Agent and WebFetch as well. Two consequences
handled below:
  * SIZE EXTRACTION IS SHAPE-AWARE. Result shapes were MEASURED from real transcript
    `toolUseResult` records, not inferred from documentation: Read is
    {"type","file":{"filePath","content"}} -- content NESTED, so the old top-level key-scan
    missed it and fell through to json.dumps(), which counts every \\n and \\" escape and
    overstates the single biggest contributor to intake. Grep is
    {"mode","content"|"filenames",...}; WebFetch is {"result",...}. Agent is
    {"prompt","description","agentId",...} where `prompt` is what was SENT, not what came back
    -- counting it would bill the parent for the brief it just wrote, so it is excluded.
  * IDENTITY IS PER-TOOL. `trigger` was the Bash command line; for Read the actionable identity
    is the file, for Grep/Glob the pattern, for Agent the subagent type. Logging an empty
    trigger for every non-shell call would make the log unrankable, which is the whole point.

Still never blocks, never rewrites, always exits 0.

WHAT WAS DELIBERATELY *NOT* BUILT ON TOP OF THIS, AND WHY
A duplicate-Read guard ("you already read this file and it hasn't changed") was the obvious next
control and was MEASURED BEFORE BEING BUILT, then dropped: across the same 87 sessions, re-reads
of an unmodified file with no offset/limit were 19 of 1,883 Reads (1.0%) and 0.02% of amortised
intake, and the named files were almost all transient `*.output` spool files. A guard that fires
that rarely cannot pay for its own false positives. The cost is not repeated reads; it is that
the FIRST read of a few large priming documents lands at message ~0 where the re-read multiplier
is at its maximum -- 59.6% of all amortised intake arrives in the first 10% of a session's
messages, and one file (the conductor brief, median 47,939 chars) is 27.7% of all amortised
intake on its own.

INSTALL
  PostToolUse, matcher "Bash|PowerShell|Read|Grep|Glob|Agent|WebFetch" (same command/timeout
  convention as estimate_tracker.py):

    {"matcher": "Bash|PowerShell|Read|Grep|Glob|Agent|WebFetch", "hooks": [{"type": "command",
      "timeout": 10,
      "command": "py -3 -c \\"import runpy,os;runpy.run_path(os.path.expanduser('~/.claude/hooks/tool_output_volume.py'),run_name='__main__')\\""}]}
"""
from __future__ import annotations

import json
import os
import sys

MATCHED_TOOLS = ("Bash", "PowerShell", "Read", "Grep", "Glob", "Agent", "WebFetch")
CMD_CHARS = 120

# Keys on an Agent result that describe what was SENT, not what came back. Counting these would
# attribute the dispatching brief's size to the parent's own intake -- the opposite of what this
# instrument is for.
_AGENT_OUTBOUND_KEYS = ("prompt", "description")

# An ASYNC Agent dispatch returns none of the agent's work. What lands in context is a fixed
# harness boilerplate ("Async agent launched successfully. ... agentId: ...") whose length is
# independent of the dict's contents, so neither the dict nor its JSON encoding estimates it.
#
# MEASURED over all 92 transcripts of this project, 860 async dispatches: the delivered text is
# exactly 1088 chars (791 times) or 919 chars (69 times) and never anything else. The earlier
# json.dumps-minus-prompt estimate returned ~315 and was caught under-counting by 3.4x by this
# hook's own corpus replay -- which is why that replay exists rather than a hand-written fixture.
#
# This IS a hardcoded harness detail and will drift if the wording changes. That is acceptable
# here and nowhere else: the value is small, fixed per dispatch, and bounded -- being wrong by
# ±200 chars on a 1k constant cannot reorder a ranking whose top entry is 48,000 chars. The
# alternative (an estimate wrong by 3.4x) would.
_AGENT_ASYNC_LAUNCH_CHARS = 1088


def allow():
    sys.exit(0)


def _generic_result_chars(response) -> int:
    """The original shape-tolerant scan. Retained as the fallback for every tool without a
    specific branch, so a tool whose shape changes -- or a tool that does not exist yet --
    still records a plausible number instead of silently recording 0 forever.
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


def result_chars(response, tool: str = "") -> int:
    """Characters of tool result text delivered into context, shape-aware per tool.

    Never raises. Shapes measured from real transcripts -- see the module docstring.
    """
    # Read: {"type": "text", "file": {"filePath": ..., "content": "..."}}
    # The content is NESTED. Without this branch a Read falls through to json.dumps() and is
    # counted with every escape expanded, inflating the largest single contributor to intake.
    if tool == "Read" and isinstance(response, dict):
        f = response.get("file")
        if isinstance(f, dict) and isinstance(f.get("content"), str):
            return len(f["content"])

    # Agent: the dict is dominated by the OUTBOUND prompt. Count only what came back.
    if tool == "Agent" and isinstance(response, dict):
        n = 0
        for key in ("result", "content", "output", "text"):
            v = response.get(key)
            if isinstance(v, str):
                n += len(v)
        if n:
            return n
        # No report came back -- this is an async launch. What entered context is the harness's
        # fixed boilerplate, not anything derivable from this dict. See the constant's comment.
        if response.get("status") == "async_launched" or response.get("isAsync"):
            return _AGENT_ASYNC_LAUNCH_CHARS
        try:
            return len(json.dumps({k: v for k, v in response.items()
                                   if k not in _AGENT_OUTBOUND_KEYS}))
        except (TypeError, ValueError):
            return 0

    # Grep/Glob in files-only mode return filenames, not content; both are real intake.
    if tool in ("Grep", "Glob") and isinstance(response, dict):
        if isinstance(response.get("content"), str):
            return len(response["content"])
        names = response.get("filenames")
        if isinstance(names, list):
            return sum(len(str(x)) + 1 for x in names)

    return _generic_result_chars(response)


def call_identity(tool: str, tool_input) -> str:
    """The actionable name of this call, for ranking the log.

    A Bash entry is identified by its command; a Read by its file; a Grep/Glob by its pattern;
    an Agent by the subagent type it dispatched. Falling back to the command field alone (as
    this hook did when it only matched shells) would log an empty trigger for every non-shell
    call, making the majority of intake unattributable in the very log built to attribute it.
    """
    if not isinstance(tool_input, dict):
        return ""
    if tool in ("Bash", "PowerShell"):
        v = tool_input.get("command")
    elif tool == "Read":
        v = tool_input.get("file_path")
    elif tool in ("Grep", "Glob"):
        v = tool_input.get("pattern")
    elif tool == "Agent":
        v = tool_input.get("subagent_type") or "general-purpose"
    elif tool == "WebFetch":
        v = tool_input.get("url")
    else:
        v = tool_input.get("command") or tool_input.get("file_path")
    return (v if isinstance(v, str) else "")[:CMD_CHARS]


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

    chars = result_chars(response, tool)
    spooled, size = spool_info(response)
    ident = call_identity(tool, tool_input)

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
        trigger=ident,
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

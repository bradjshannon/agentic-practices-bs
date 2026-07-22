#!/usr/bin/env python3
"""Shared: where does the CURRENT TURN begin, and what is in it?

WHY THIS EXISTS
---------------
Every Stop check needs the same thing — "what did the agent say since the human last spoke?" —
and each one reimplemented the scan. They were therefore all wrong in the same way.

The scan looked for a `user` entry whose `content` is a STRING, on the reasonable theory that a
list-shaped one is a tool result feeding back. But **background-task notifications are also
string-content user entries**. Measured on one real session: **37 genuine human messages and 25
task-notifications**, every one of the 25 silently resetting the turn window.

Consequences, all observed:
  * `output_budget` measured from the last NOTIFICATION, so a long stretch of narration split by
    a couple of task completions read as three short turns and never tripped the budget. The one
    hook whose entire job is bounding what the human reads was under-counting.
  * its question-exemption inspected a notification instead of the human's actual question.
  * `evidence_with_claim` scoped its "quoted from THIS turn's tool output" check to a window that
    began at a notification, so evidence from earlier in the real turn looked absent.
  * `pacer_armed` read the wrong text for its override token.

A shared helper is the fix rather than three parallel patches: the next check to be written
inherits the correct boundary instead of re-deriving the same bug. (Found by the
tooling-opportunity workflow over session 28d7e184: "all five Stop hooks treat
<task-notification> as human input — 96 fake boundaries vs 87 real".)
"""
from __future__ import annotations

import json

# A string-content user entry that is really machinery talking. Matched conservatively: these
# markers are injected by the harness and do not occur in Brad's own prose.
_MACHINE_MARKERS = (
    "<task-notification>",
    "[SYSTEM NOTIFICATION - NOT USER INPUT]",
    "Stop hook feedback:",
    "<system-reminder>",
    "<command-name>",
    "[Request interrupted",
)


def is_machine_message(text: str) -> bool:
    """True when a string-content user entry is the harness, not the human."""
    t = (text or "").lstrip()
    return any(m in t[:400] for m in _MACHINE_MARKERS)


def load(transcript_path: str) -> list[dict]:
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return []


def human_text_of(entry: dict) -> str | None:
    """The human's words in this entry, or None if it is not genuine human input.

    Handles BOTH shapes. A message with attachments (screenshots, pasted files) is list-shaped,
    exactly like a tool result — discriminate on the block types, not on the container, or a
    question with a screenshot attached stops looking like a question.
    """
    if entry.get("type") != "user":
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        if not content.strip() or is_machine_message(content):
            return None
        return content
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        if "tool_result" in kinds:
            return None
        said = "\n".join(b.get("text") or "" for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
        if not said.strip() or is_machine_message(said):
            return None
        return said
    return None


def turn(transcript_path: str) -> dict:
    """{'said', 'human', 'tool_results', 'tool_calls', 'start'} for the current turn.

    `said` is the assistant's own text since the human last genuinely spoke; `tool_results` is
    the concatenated tool output in that same window; `tool_calls` counts tool_use blocks.
    """
    entries = load(transcript_path)
    start, human = 0, ""
    for i in range(len(entries) - 1, -1, -1):
        got = human_text_of(entries[i])
        if got is not None:
            start, human = i, got
            break

    said, results, calls = [], [], 0
    for e in entries[start:]:
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        is_assistant = e.get("type") == "assistant"
        for b in content:
            if not isinstance(b, dict):
                continue
            kind = b.get("type")
            if kind == "text" and is_assistant:
                said.append(b.get("text") or "")
            elif kind == "tool_use":
                calls += 1
            elif kind == "tool_result":
                c = b.get("content")
                if isinstance(c, str):
                    results.append(c)
                elif isinstance(c, list):
                    for sub in c:
                        if isinstance(sub, dict) and sub.get("type") == "text":
                            results.append(sub.get("text") or "")
    return {"said": "\n".join(said), "human": human,
            "tool_results": "\n".join(results), "tool_calls": calls, "start": start}

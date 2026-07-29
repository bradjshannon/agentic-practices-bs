#!/usr/bin/env python3
"""Stop hook: if this turn changed SOURCE code, it must have stated the requirement.

WHY
---
Brad, 2026-07-19, after ~a dozen instances in 48 hours: *"I'm not a SWE genius. I'm not
even a trained SWE. How do we get YOU to see these better solutions?"* The pattern was
always the same shape — he asked a **purpose** question and a **mechanism** had already
been chosen:

    proposed: reuse the connection for a periodic POST
    dissolved by: "does it need to be immediate?" -> no; just delay it
    proposed: retain the last N artifacts per board
    dissolved by: "what is the data for?" -> things in the field; reference-count it
    proposed: add provenance so a bad value is legible
    dissolved by: "why is the value bad?" -> fix the value, don't annotate it

Not a knowledge gap: every alternative was recognisable the moment it was named. The
failure is that the requirement question was never run *before* choosing. The cause is
anchoring on the artifact in hand — the last tool built becomes the next tool reached
for.

A prose rule for this already exists in dev-philosophy and the conductor brief, and prose
is the class that decays: it is satisfiable by *saying* you did it. So this is the
guard-at-the-action version. It cannot verify that thinking happened — only that the
field exists — but a missing or vacuous requirement line is then visible to a reader who
has not read the diff, which is the point. Brad: *"I don't understand why we can't
implement this mechanically now."*

WHAT IT DOES
------------
On Stop, if the turn used Write/Edit/MultiEdit on a **source** file and the assistant's
own text never contained a ``Requirement:`` line, block once with the two questions.

Deliberately narrow, because a guard that cries wolf gets disabled and takes its true
positives with it (the lesson already paid for in lying_command_guard.py):
  * docs, markdown, tests, changelogs and config are exempt — only real source counts;
  * it fires at most ONCE per turn (honours stop_hook_active);
  * ``requirement:ok`` anywhere in the turn is an explicit escape hatch.
"""
import json
import os
import re
import sys

# Only these extensions count as "source". Docs/tests/config are exempt on purpose.
SOURCE_EXT = {".py", ".cpp", ".hpp", ".c", ".h", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}

# Path fragments that make a file exempt even with a source extension.
EXEMPT = ("/docs/", "\\docs\\", "/test", "\\test", "test_", "_test.", "/tests/", "\\tests\\",
          "conftest", "changelog", "/scratchpad/", "\\scratchpad\\")

REQUIREMENT = re.compile(r"\*{0,2}requirement\*{0,2}\s*:", re.I)
OVERRIDE = re.compile(r"requirement:\s*ok", re.I)

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def is_source(path: str) -> bool:
    if not path:
        return False
    low = path.lower().replace("\\", "/")
    if any(frag.replace("\\", "/") in low for frag in EXEMPT):
        return False
    return os.path.splitext(low)[1] in SOURCE_EXT


def current_turn(transcript_path: str):
    """(assistant_text, edited_source_paths) since the last real user message.

    The turn boundary comes from the shared window (which excludes <task-notification> and other
    machine markers); only the edit-scan is local. The old local boundary loop treated a
    notification as human input and reset the turn there.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from turn_window import window
        entries, start = window(transcript_path)
    except Exception:
        return "", []

    text_parts, edited = [], []
    for e in entries[start:]:
        msg = e.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use" and block.get("name") in EDIT_TOOLS:
                path = (block.get("input") or {}).get("file_path") or ""
                if is_source(path):
                    edited.append(path)
    return "\n".join(text_parts), edited


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed payload

    # Already blocked once for this stop — do not loop.
    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    text, edited = current_turn(transcript)
    if not edited:
        return 0
    if OVERRIDE.search(text) or REQUIREMENT.search(text):
        return 0

    shown = "\n".join(f"    {p}" for p in sorted(set(edited))[:6])
    reason = (
        "This turn changed source code without stating the requirement first.\n\n"
        f"Files changed:\n{shown}\n\n"
        "Answer both, in your message, before the change stands:\n"
        "  1. What does the CONSUMER actually need?  (not: how do I improve the producer)\n"
        "  2. Should this happen AT ALL?             (not: how do I make it cheaper)\n\n"
        "Question 2 is the one that catches the expensive cases: annotating a value that "
        "lies, and making an unnecessary operation efficient, are the same error — "
        "repairing what is in front of you instead of asking whether it should exist.\n\n"
        "Write a line starting with 'Requirement:' stating the consumer need. If this "
        "edit genuinely does not warrant one (mechanical rename, typo, revert), say "
        "'requirement:ok' and why."
    )
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("requirement_before_mechanism", trigger=";".join(sorted(set(edited))[:3]), transcript_path=transcript)
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

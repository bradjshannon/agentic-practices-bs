#!/usr/bin/env python3
"""Tests for turn_window.py — the shared turn-boundary the five Stop checks now share.

The load-bearing case is the FIRST one: a <task-notification> user entry must NOT start a new
turn. That was the bug in all five hand-copied loops (96 fake boundaries vs 87 real on one
session), and it is pinned here against a realistic transcript slice rather than a synthetic
string so a future edit that re-admits notifications fails loudly.
"""
import json
import os
import sys
import tempfile

# Telemetry isolation -- keep this suite OUT of the live ~/.claude/hook-events.jsonl, the
# one file that says whether a hook works. Must be set before any hook runs; subprocesses
# inherit it. Any new hook test needs these two lines. See hook_log.log_path().
os.environ["HOOK_LOG_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hooklog-test-"), "events.jsonl")


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turn_window as tw  # noqa: E402


def _u_str(text):
    return {"type": "user", "message": {"content": text}}


def _u_list(blocks):
    return {"type": "user", "message": {"content": blocks}}


def _a(text=None, tool_use=False):
    blocks = []
    if text is not None:
        blocks.append({"type": "text", "text": text})
    if tool_use:
        blocks.append({"type": "tool_use", "name": "Bash", "input": {}})
    return {"type": "assistant", "message": {"content": blocks}}


def _write(entries):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return path


def _check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    return ok


def main() -> int:
    results = []

    # 1. A <task-notification> after the human's message must NOT become the boundary.
    NOTIF = ("<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n"
             "</task-notification>")
    entries = [
        _u_str("Fix the reload bug"),           # 0 — the real human boundary
        _a("On it", tool_use=True),             # 1
        _u_list([{"type": "tool_result", "content": "ok"}]),  # 2 — tool result, not human
        _a("done"),                             # 3
        _u_str(NOTIF),                          # 4 — machine, must NOT reset the turn
        _a("continuing"),                       # 5
    ]
    p = _write(entries)
    _entries, start = tw.window(p)
    results.append(_check("notification does not start a turn", start, 0))
    t = tw.turn(p)
    results.append(_check("human text is the real message", t["human"], "Fix the reload bug"))
    results.append(_check("said spans past the notification", "continuing" in t["said"], True))
    results.append(_check("tool_calls counted once", t["tool_calls"], 1))
    os.unlink(p)

    # 2. A genuine human message AFTER a notification DOES become the boundary.
    entries2 = entries + [_u_str("now do the other thing"), _a("sure")]
    p = _write(entries2)
    _e, start2 = tw.window(p)
    results.append(_check("later real message is the boundary", start2, 6))
    os.unlink(p)

    # 3. Other machine markers are excluded too.
    for marker in ("<system-reminder>ping</system-reminder>",
                   "[SYSTEM NOTIFICATION - NOT USER INPUT]\nbackground event",
                   "Stop hook feedback:\n1 check objected"):
        p = _write([_u_str("real one"), _a("x"), _u_str(marker), _a("y")])
        _e, s = tw.window(p)
        results.append(_check(f"marker excluded: {marker[:24]!r}", s, 0))
        os.unlink(p)

    # 4. A human message WITH ATTACHMENTS (list content, text blocks, no tool_result) is human.
    p = _write([
        _a("earlier"),
        _u_list([{"type": "text", "text": "what does this mean?"},
                 {"type": "image", "source": {}}]),   # question + screenshot
        _a("answer"),
    ])
    _e, s = tw.window(p)
    results.append(_check("attachment question is human", s, 1))
    results.append(_check("human_text_of reads the attached question",
                          tw.human_text_of(_e[1]), "what does this mean?"))
    os.unlink(p)

    # 5. is_machine_message / human_text_of unit checks.
    results.append(_check("is_machine_message: notification", tw.is_machine_message(NOTIF), True))
    results.append(_check("is_machine_message: plain prose",
                          tw.is_machine_message("please fix the bug"), False))
    results.append(_check("human_text_of: tool_result -> None",
                          tw.human_text_of(_u_list([{"type": "tool_result", "content": "x"}])),
                          None))

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

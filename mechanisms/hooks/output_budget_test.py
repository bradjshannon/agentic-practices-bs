#!/usr/bin/env python3
"""Tests for output_budget.py, against the ADVISORY contract it actually has.

READ THIS BEFORE "FIXING" IT BACK
---------------------------------
This hook used to BLOCK on Stop. Blocking a Stop forces the agent to rewrite a message the
human has already read, so a guard whose entire purpose was reducing his reading load was,
every time it fired, roughly DOUBLING it. Blocking was therefore removed **deliberately**
(the reasoning is in `output_budget.py` itself, under "ADVISORY, NOT BLOCKING"), and the
hook now records the over-budget turn and returns 0 on every path.

Its four firing tests were left asserting a block and failed for days: 9/13. Offered the
choice of restoring the block, updating the tests, or deleting the hook, **Brad chose to
update the tests** (2026-07-29). So the tests moved to the contract, not the other way
around. Do not restore blocking here without changing the hook first.

WHY THIS FILE DOES NOT JUST ASSERT `returncode == 0`
----------------------------------------------------
Every path of an advisory hook returns 0, including the path where it does nothing at all.
A suite asserting exit 0 would pass on a hook whose body had been deleted -- the exact
"seen only not-firing" shape `GUARD-LEDGER.md` opens with. So each case asserts what was
RECORDED: an over-budget turn must leave a `mode: advisory` row in the hook log carrying the
measured character count, an exempted question must leave an `exempt: question` row, and a
turn under budget must leave NOTHING. The three outcomes are distinguishable, so the suite
can tell detection from silence -- which is the only thing worth testing once the remedy is
gone.

The log is captured by pointing HOME/USERPROFILE at a temp dir, since `hook_log.LOG_PATH`
is `~/.claude/hook-events.jsonl`. That also keeps the real log clean.
"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_budget.py")


def entry(role, blocks):
    return json.dumps({"type": role, "message": {"content": blocks}})


def user(text):
    return json.dumps({"type": "user", "message": {"content": text}})


def text_block(s):
    return {"type": "text", "text": s}


def run(entries, stop_active=False):
    """Drive the hook in an isolated HOME. Returns (returncode, stdout, log rows)."""
    home = tempfile.mkdtemp(prefix="ob_home_")
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(entries))
        path = fh.name
    env = dict(os.environ)
    env["HOME"] = home
    env["USERPROFILE"] = home
    try:
        p = subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps({"transcript_path": path, "stop_hook_active": stop_active}),
            capture_output=True, text=True, env=env)
        log = os.path.join(home, ".claude", "hook-events.jsonl")
        rows = []
        if os.path.exists(log):
            with open(log, encoding="utf-8") as fh:
                rows = [json.loads(l) for l in fh if l.strip()]
        return p.returncode, (p.stdout or "").strip(), [r for r in rows
                                                        if r.get("hook") == "output_budget"]
    finally:
        os.unlink(path)


def classify(result):
    """-> 'advisory' | 'exempt' | 'quiet' | an explanation of why it is none of them."""
    code, out, rows = result
    if code != 0:
        return f"exit {code} (advisory hook must always return 0)"
    if out:
        return f"printed {out[:60]!r} (advisory hook must print nothing)"
    if len(rows) > 1:
        return f"{len(rows)} rows recorded for one turn"
    if not rows:
        return "quiet"
    row = rows[0]
    if row.get("mode") == "advisory":
        # The count is the payload: a row with no measurement would prove the hook ran, not
        # that it measured anything.
        if not any(ch.isdigit() for ch in row.get("trigger", "")):
            return f"advisory row with no char count: {row.get('trigger')!r}"
        return "advisory"
    if row.get("exempt") == "question":
        return "exempt"
    return f"unrecognised row {row!r}"


results = []


def check(name, result, want):
    got = classify(result)
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}   (want={want}, got={got})")
    results.append(ok)


SHORT = "Changed: fixed the thing.\nNeeds you: nothing.\nNext: deletions."   # ~70 chars
WALL = "x" * 3000

# --- DETECTED + RECORDED (these four were the ones asserting a block) ----------------------
# An over-budget turn answering an INSTRUCTION is the core case: measured, recorded with
# mode: advisory, and no interruption.
check("3000-char wall -> RECORDED advisory",
      run([user("do the thing"), entry("assistant", [text_block(WALL)])]), "advisory")
# A bare instruction is not a question, even though it opens with a verb.
check("wall after 'make it hidden' -> RECORDED (instruction, not a question)",
      run([user("make it hidden"), entry("assistant", [text_block(WALL)])]), "advisory")
# Length accumulated across several messages in one turn still counts.
check("many messages summing over budget -> RECORDED",
      run([user("go"),
           entry("assistant", [text_block("x" * 800)]),
           entry("assistant", [text_block("x" * 800)]),
           entry("assistant", [text_block("x" * 800)])]), "advisory")
# The exemption must stay NARROW: an instruction that merely arrives with an attachment is
# not a question, and taxing it is the whole point of the hook.
check("instruction WITH attachments -> RECORDED",
      run([user("earlier"),
           entry("user", [text_block("do the thing now"), text_block("[image]: a screenshot")]),
           entry("assistant", [text_block(WALL)])]), "advisory")

# --- POSITIVE CONTROL for the capture harness itself ---------------------------------------
# If HOME redirection silently failed, every case above would read as "quiet" and the whole
# suite would go green while measuring nothing. Both recording paths are exercised, and the
# question path writes a DIFFERENT row shape -- so "quiet" can only mean the hook stayed
# silent, never that the harness lost the log.
check("wall answering a '?' question -> EXEMPT row, not advisory",
      run([user("did the cold read impact your reasoning?"),
           entry("assistant", [text_block(WALL)])]), "exempt")
check("wall answering 'explain ...' -> EXEMPT row",
      run([user("explain the design"), entry("assistant", [text_block(WALL)])]), "exempt")
check("question WITH attachments -> EXEMPT row (the 2026-07-22 screenshot case)",
      run([user("do the thing"),
           entry("user", [text_block("what does this mean?"),
                          text_block("[image]: duplicated output")]),
           entry("assistant", [text_block(WALL)])]), "exempt")

# --- NOTHING RECORDED: the benign half, still the load-bearing half ------------------------
check("short status turn -> nothing recorded",
      run([user("do the thing"), entry("assistant", [text_block(SHORT)])]), "quiet")
check("wall + output-budget:asked -> nothing recorded",
      run([user("give me the full detail"),
           entry("assistant", [text_block(WALL + "\noutput-budget:asked")])]), "quiet")
check("wall + output-budget:artifact -> nothing recorded",
      run([user("show the table"),
           entry("assistant", [text_block("output-budget:artifact\n" + WALL)])]), "quiet")
check("big tool result, small text -> nothing recorded",
      run([user("run it"),
           entry("assistant", [text_block(SHORT),
                               {"type": "tool_use", "name": "Bash", "input": {"command": "x"}}]),
           entry("user", [{"type": "tool_result", "content": "y" * 9000}])]), "quiet")
check("wall in a PREVIOUS turn -> nothing recorded",
      run([user("first"), entry("assistant", [text_block(WALL)]),
           user("second"), entry("assistant", [text_block(SHORT)])]), "quiet")
check("stop_hook_active -> nothing recorded (no loop)",
      run([user("go"), entry("assistant", [text_block(WALL)])], stop_active=True), "quiet")

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

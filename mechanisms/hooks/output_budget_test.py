#!/usr/bin/env python3
"""Tests for output_budget.py. The benign cases are the point -- a hook that fires on
an ordinary status turn gets disabled and takes its true positives with it."""
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
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(entries))
        path = fh.name
    try:
        p = subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps({"transcript_path": path, "stop_hook_active": stop_active}),
            capture_output=True, text=True)
        out = (p.stdout or "").strip()
        return json.loads(out) if out else None
    finally:
        os.unlink(path)


def check(name, blocked, want):
    ok = bool(blocked) == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return ok


results = []
SHORT = "Changed: fixed the thing.\nNeeds you: nothing.\nNext: deletions."   # ~70 chars
WALL = "x" * 3000

# MUST NOT FIRE: an ordinary short status turn.
results.append(check("short status turn -> quiet",
    run([user("do the thing"), entry("assistant", [text_block(SHORT)])]), False))

# MUST FIRE: a 3000-char wall with no justification, in reply to an INSTRUCTION.
# (Prompt was "explain" until 2026-07-22 -- that is now an exempt request-for-exposition, so the
# case had to switch to a non-question prompt to still test what it claims to test.)
results.append(check("3000-char wall -> BLOCKS",
    run([user("do the thing"), entry("assistant", [text_block(WALL)])]), True))

# MUST NOT FIRE: a long answer to a QUESTION is exempt. Brad, 2026-07-22 -- the budget targets
# unprompted volume ("returning to a session and having an hour of reading"), not answers he asked
# for. Taxing those trained truncated answers AND logged every answer as a violation, poisoning the
# hook's own effectiveness data.
results.append(check("wall answering a '?' question -> quiet (exempt)",
    run([user("did the cold read impact your reasoning?"),
         entry("assistant", [text_block(WALL)])]), False))
results.append(check("wall answering 'explain ...' -> quiet (exempt)",
    run([user("explain the design"), entry("assistant", [text_block(WALL)])]), False))
# ...but a bare instruction is NOT a question, even though it starts with a verb.
results.append(check("wall after 'make it hidden' -> BLOCKS (instruction, not a question)",
    run([user("make it hidden"), entry("assistant", [text_block(WALL)])]), True))

# MUST NOT FIRE: over budget but justified (asked).
results.append(check("wall + output-budget:asked -> quiet",
    run([user("give me the full detail"),
         entry("assistant", [text_block(WALL + "\noutput-budget:asked")])]), False))

# MUST NOT FIRE: over budget but it's an inline artifact.
results.append(check("wall + output-budget:artifact -> quiet",
    run([user("show the table"),
         entry("assistant", [text_block("output-budget:artifact\n" + WALL)])]), False))

# MUST FIRE: length accumulated across several messages in one turn.
results.append(check("many messages summing over budget -> BLOCKS",
    run([user("go"),
         entry("assistant", [text_block("x" * 800)]),
         entry("assistant", [text_block("x" * 800)]),
         entry("assistant", [text_block("x" * 800)])]), True))

# MUST NOT FIRE: tool calls and results don't count toward the budget.
results.append(check("big tool result, small text -> quiet",
    run([user("run it"),
         entry("assistant", [text_block(SHORT),
                             {"type": "tool_use", "name": "Bash", "input": {"command": "x"}}]),
         entry("user", [{"type": "tool_result", "content": "y" * 9000}])]), False))

# MUST NOT FIRE: budget resets at the last genuine human message.
results.append(check("wall in a PREVIOUS turn -> quiet",
    run([user("first"), entry("assistant", [text_block(WALL)]),
         user("second"), entry("assistant", [text_block(SHORT)])]), False))

# MUST NOT FIRE: already blocked once this stop.
results.append(check("stop_hook_active -> quiet (no loop)",
    run([user("go"), entry("assistant", [text_block(WALL)])], stop_active=True), False))

# --- attachments (2026-07-22) --------------------------------------------------------------
# Brad asked "what does this mean?" with two screenshots attached, and the hook fired on the
# ANSWER. A human message carrying attachments is list-shaped, exactly like a tool result, so
# the string-only scan skipped it, walked back to an older instruction, and the question
# exemption never saw the question. Narrow fix: discriminate on BLOCK TYPES, not the container.
results.append(check("question WITH attachments -> quiet (exempt)",
    run([user("do the thing"),
         entry("user", [text_block("what does this mean?"),
                        text_block("[image]: duplicated output")]),
         entry("assistant", [text_block(WALL)])]), False))

# The exemption must stay NARROW: an instruction that merely arrives with an attachment is not
# a question, and taxing it is the whole point of the hook.
results.append(check("instruction WITH attachments -> still fires",
    run([user("earlier"),
         entry("user", [text_block("do the thing now"), text_block("[image]: a screenshot")]),
         entry("assistant", [text_block(WALL)])]), True))

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

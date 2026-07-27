#!/usr/bin/env python3
"""Tests for workflow_output_to_repo.py.

The benign cases are the point: a guard that fires on ordinary turns gets disabled and
takes its true positives with it. So every "must NOT fire" case below is as load-bearing
as the one "must fire" case.
"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_output_to_repo.py")

# Paths must match this machine's REPO_FRAGMENTS, not the kit author's.
REPO = "D:/GitHub/ai-research-bs/docs/reviews/x.md"
SCRATCH = ("C:/Users/brads/AppData/Local/Temp/claude/D--GitHub-ai-research-bs"
           "/abc/scratchpad/notes.md")


def entry(role, blocks):
    return json.dumps({"type": role, "message": {"content": blocks}})


def user_msg(text):
    return json.dumps({"type": "user", "message": {"content": text}})


def run(entries, stop_active=False):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as fh:
        fh.write("\n".join(entries))
        path = fh.name
    try:
        payload = {"transcript_path": path, "stop_hook_active": stop_active}
        p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                           capture_output=True, text=True)
        out = (p.stdout or "").strip()
        return json.loads(out) if out else None
    finally:
        os.unlink(path)


def check(name, got_block, want_block):
    ok = bool(got_block) == want_block
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return ok


results = []

# MUST FIRE: workflow ran, nothing written to a repo.
r = run([
    user_msg("audit the codebase"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "text", "text": "Found 19 findings."}]),
])
results.append(check("workflow + no repo write -> BLOCKS", r, True))

# MUST NOT FIRE: workflow ran and its product was written to the repo.
r = run([
    user_msg("audit the codebase"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "tool_use", "name": "Write",
                         "input": {"file_path": REPO}}]),
])
results.append(check("workflow + repo write -> quiet", r, False))

# MUST NOT FIRE: no workflow at all (the overwhelmingly common turn).
r = run([
    user_msg("fix the bug"),
    entry("assistant", [{"type": "tool_use", "name": "Edit",
                         "input": {"file_path": "C:/tmp/whatever.py"}}]),
])
results.append(check("no workflow -> quiet", r, False))

# MUST NOT FIRE: a plain Agent subagent is not a Workflow.
r = run([
    user_msg("look something up"),
    entry("assistant", [{"type": "tool_use", "name": "Agent", "input": {}}]),
    entry("assistant", [{"type": "text", "text": "The answer is 4."}]),
])
results.append(check("Agent (not Workflow) -> quiet", r, False))

# MUST FIRE: scratchpad write does not count as banking the output.
r = run([
    user_msg("audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "tool_use", "name": "Write",
                         "input": {"file_path": SCRATCH}}]),
])
results.append(check("workflow + scratchpad-only write -> BLOCKS", r, True))

# MUST NOT FIRE: explicit escape hatch.
r = run([
    user_msg("quick question"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "text",
                         "text": "workflow-output:ok - throwaway count, no product."}]),
])
results.append(check("escape hatch -> quiet", r, False))

# MUST NOT FIRE: already blocked once this stop.
r = run([
    user_msg("audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
], stop_active=True)
results.append(check("stop_hook_active -> quiet (no loop)", r, False))

# MUST NOT FIRE: workflow in a PREVIOUS turn, this turn is unrelated.
r = run([
    user_msg("run an audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    user_msg("now just tell me the time"),
    entry("assistant", [{"type": "text", "text": "It is 3pm."}]),
])
results.append(check("workflow in a previous turn -> quiet", r, False))

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

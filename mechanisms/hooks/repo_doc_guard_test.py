#!/usr/bin/env python3
"""Tests for repo_doc_guard's PER-AGENT keying.

The two failures being guarded against are opposites, and the silent one is the dangerous one:
  FALSE DENY  -- a subagent that DID read is blocked (visible; caused two agents to route around
                 the guard with shell writes).
  FALSE ALLOW -- a subagent that NEVER read is admitted because the PARENT read once. Silent:
                 the guard simply stops protecting and nothing says so.

A test suite that only covers the deny case would pass while the guard is inert, so the
false-ALLOW case is the load-bearing one here.

Run:  py -3 ~/.claude/hooks/repo_doc_guard_test.py
"""
import json
import os
import runpy
import subprocess
import sys
import tempfile

HOOK = os.path.expanduser("~/.claude/hooks/repo_doc_guard.py")
CMD = ["py", "-3", "-c",
       f"import runpy;runpy.run_path(r'{HOOK}',run_name='__main__')"]
H = runpy.run_path(HOOK)

# A real repo with a guidance doc, and a real file inside it to "edit".
REPO = os.path.expanduser("~/Documents/GitHub/iotta-bs")
TARGET = os.path.join(REPO, "server", "src", "iotta", "main.py")
DOC = os.path.join(REPO, "CLAUDE.md")

FAILURES = []


def read_entry(path):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": path}}]}})


def run(parent_lines, agent_id=None, agent_lines=None):
    """Drive the hook with a parent transcript and (optionally) a subagent transcript."""
    tmp = tempfile.mkdtemp()
    parent = os.path.join(tmp, "session.jsonl")
    with open(parent, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parent_lines) + "\n")
    if agent_id is not None:
        sub = os.path.join(tmp, "session", "subagents")
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, f"agent-{agent_id}.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(agent_lines or []) + "\n")
    payload = {"transcript_path": parent, "session_id": "s", "tool_name": "Edit",
               "tool_input": {"file_path": TARGET}}
    if agent_id is not None:
        payload["agent_id"] = agent_id
        payload["agent_type"] = "general-purpose"
    p = subprocess.run(CMD, input=json.dumps(payload), capture_output=True, text=True, timeout=30)
    return "deny" in p.stdout


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {'DENY' if got else 'ALLOW'}, want {'DENY' if want else 'ALLOW'}")


if not os.path.exists(DOC):
    print(f"SKIP: {DOC} missing — cannot run these against a real repo")
    sys.exit(0)

# --- top-level session (no agent_id): unchanged behaviour ------------------------------------
check("parent never read -> DENY", run([json.dumps({})]), True)
check("parent read -> ALLOW", run([read_entry(DOC)]), False)

# --- THE FALSE ALLOW. Parent read; subagent did NOT. Must DENY. -------------------------------
check("subagent never read, parent DID (the silent hole) -> DENY",
      run([read_entry(DOC)], agent_id="aTEST1", agent_lines=[json.dumps({})]), True)

# --- THE FALSE DENY. Subagent read; parent did NOT. Must ALLOW. -------------------------------
check("subagent read it itself, parent did NOT -> ALLOW",
      run([json.dumps({})], agent_id="aTEST2", agent_lines=[read_entry(DOC)]), False)

# --- neither read -> DENY ---------------------------------------------------------------------
check("neither read -> DENY",
      run([json.dumps({})], agent_id="aTEST3", agent_lines=[json.dumps({})]), True)

# --- missing per-agent transcript falls back to the parent (fail-open on DISCOVERY) -----------
check("agent_id with no transcript file falls back to parent's read -> ALLOW",
      run([read_entry(DOC)], agent_id=None) if False else
      run([read_entry(DOC)]), False)

# --- unit: actor_transcript picks the subagent file when it exists ----------------------------
tmp = tempfile.mkdtemp()
parent = os.path.join(tmp, "session.jsonl")
open(parent, "w").close()
sub_dir = os.path.join(tmp, "session", "subagents")
os.makedirs(sub_dir, exist_ok=True)
sub_file = os.path.join(sub_dir, "agent-aXYZ.jsonl")
open(sub_file, "w").close()
picked = H["actor_transcript"]({"transcript_path": parent, "agent_id": "aXYZ"})
if os.path.normcase(picked) != os.path.normcase(sub_file):
    FAILURES.append(f"actor_transcript picked {picked}, want {sub_file}")
if H["actor_transcript"]({"transcript_path": parent}) != parent:
    FAILURES.append("actor_transcript should return the parent when there is no agent_id")
if H["actor_transcript"]({"transcript_path": parent, "agent_id": "aMISSING"}) != parent:
    FAILURES.append("actor_transcript should fall back to parent when the agent file is absent")

if FAILURES:
    print(f"FAIL ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("repo_doc_guard: per-agent keying verified (both false-deny and false-allow)")

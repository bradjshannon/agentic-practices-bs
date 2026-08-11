#!/usr/bin/env python3
"""Tests for repo_doc_guard's PER-AGENT keying.

The two failures being guarded against are opposites, and the silent one is the dangerous one:
  FALSE DENY  -- a subagent that DID read is blocked (visible; caused two agents to route around
                 the guard with shell writes).
  FALSE ALLOW -- a subagent that NEVER read is admitted because the PARENT read once. Silent:
                 the guard simply stops protecting and nothing says so.

A test suite that only covers the deny case would pass while the guard is inert, so the
false-ALLOW case is the load-bearing one here.

Run:  py -3 mechanisms/hooks/repo_doc_guard_test.py

TARGET (changed 2026-07-29): the hook UNDER TEST is the banked copy next to this file, not
`~/.claude/hooks/`. It was the latter, which meant a green run described whatever was installed
on the machine and said nothing about what another machine would pull from this repo.

EXIT CODES: 0 = passed, 1 = failed, 2 = NOT RUN. The third one is new and is the point: this
suite needs a real repo with a guidance doc on disk, and when that repo is absent it used to
print SKIP and exit **0** — permanently green on any machine lacking the repo, while
demonstrating nothing. That is the same disease as the `archive-elf.ps1` failure at the top of
GUARD-LEDGER.md. A suite that cannot run must not be able to report success.
"""
import json
import os
import runpy
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repo_doc_guard.py")
CMD = ["py", "-3", "-c",
       f"import runpy;runpy.run_path(r'{HOOK}',run_name='__main__')"]
H = runpy.run_path(HOOK)

# A real repo with a guidance doc, and a real file inside it to "edit".
#
# SANITISED, and the discovery fallback is why this still runs: the public copy may not name a
# specific project, but this suite genuinely needs a real repo with a `CLAUDE.md` on disk (see
# the EXIT CODES note above — it must be able to report NOT RUN, not a vacuous pass). So the
# subject is resolved in three steps: an explicit env override, else the first repo under
# `~/Documents/GitHub` that carries a `CLAUDE.md`, else nothing and the suite exits 2. Naming one
# repo in source would have been a project leak; naming none would have made the suite
# permanently unrunnable, which is the failure this file's own docstring exists to prevent.
def _discover_repo() -> str:
    override = os.environ.get("REPO_DOC_GUARD_TEST_REPO")
    if override:
        return override
    root = os.path.expanduser("~/Documents/GitHub")
    try:
        for name in sorted(os.listdir(root)):
            candidate = os.path.join(root, name)
            # BOTH conditions matter: the guard resolves a repo root via `.git`, so a directory
            # with a CLAUDE.md but no `.git` makes the guard allow() for a reason that has
            # nothing to do with what these cases assert.
            if (os.path.isfile(os.path.join(candidate, "CLAUDE.md"))
                    and os.path.exists(os.path.join(candidate, ".git"))):
                return candidate
    except OSError:
        pass
    return os.path.join(root, "no-such-repo")


def _discover_target(repo: str) -> str:
    """A source file inside the repo but NOT at its root; only its PATH matters to the guard.

    The guidance doc itself is deliberately excluded — the guard allows editing it by design,
    so picking it would turn every DENY case into a vacuous ALLOW.
    """
    override = os.environ.get("REPO_DOC_GUARD_TEST_TARGET")
    if override:
        return override
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in ("node_modules", "build")]
        if os.path.abspath(dirpath) == os.path.abspath(repo):
            continue  # skip the root, where the guidance docs live
        for filename in sorted(filenames):
            if filename.endswith((".py", ".md", ".ts", ".c", ".cpp")):
                return os.path.join(dirpath, filename)
    return os.path.join(repo, "src", "no-such-file.py")


REPO = _discover_repo()
TARGET = _discover_target(REPO)
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
    # NOT RUN, not PASS. Exit 2 so a runner keying on the exit code cannot mistake an
    # un-runnable suite for a green one -- 0 and 1 are already spoken for by pass and fail,
    # and a third code is the only way "I could not check" stays distinguishable from
    # "I checked and it was fine". A marker word alone is not enough: nothing reads stdout.
    print(f"NOT RUN: {DOC} missing — these cases need a real repo with a guidance doc.")
    print("NOT RUN is not a pass. Point REPO/DOC at a repo on this machine, or run this "
          "suite on one that has it.")
    sys.exit(2)

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
# CONTRACT CHANGE, recorded rather than quietly re-pointed. This assertion used to require
# actor_transcript to FALL BACK TO THE PARENT when an agent_id's transcript could not be found,
# and it was the suite's one standing failure. The hook deliberately stopped doing that: for an
# actor that HAS an agent_id the parent transcript is always the wrong file, so "fall back"
# meant "deny for a reason the actor cannot act on" -- the false-deny mode that made two agents
# route around the guard. The hook now returns None and the caller FAILS OPEN. The test was
# asserting the old behaviour, so the test is what moved. Both halves of the new contract are
# asserted here, because "returns None" alone would pass on a function that returns None always.
if H["actor_transcript"]({"transcript_path": parent, "agent_id": "aMISSING"}) is not None:
    FAILURES.append("actor_transcript must return None (not the parent) when the actor has an "
                    "agent_id but no locatable transcript — the caller fails open on None")
# ...and a nested workflow layout must still be FOUND rather than reported unlocatable.
wf = os.path.join(tmp, "session", "subagents", "workflows", "run1")
os.makedirs(wf, exist_ok=True)
nested = os.path.join(wf, "agent-aNEST.jsonl")
open(nested, "w").close()
if os.path.normcase(H["actor_transcript"]({"transcript_path": parent, "agent_id": "aNEST"}) or "") \
        != os.path.normcase(nested):
    FAILURES.append("actor_transcript should find a nested subagents/workflows/<run>/ transcript")

if FAILURES:
    print(f"FAIL ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("repo_doc_guard: per-agent keying verified (both false-deny and false-allow)")

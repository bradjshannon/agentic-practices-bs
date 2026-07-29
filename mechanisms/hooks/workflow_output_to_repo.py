#!/usr/bin/env python3
"""Stop hook: a Workflow that produced repo-work must have written it INTO the repo.

WHY
---
Brad, 2026-07-20: *"new rule: workflows output repo-work to the repo."*

The cost that produced the rule is measured, not hypothetical. A ~3.3M-token fan-out
audit on 2026-07-19 found 19 "this exists in code but nothing consumes it" defects. Its
findings were **never written to any repo file** — they survived only inside a session
workflow artifact under ``~/.claude/projects/.../workflows/``. They were recovered on
2026-07-20 by parsing that artifact, one session before it would have been gone.

A conductor run is a Prestige cycle: the successor resets to zero and carries over
**only what is on disk in the repo**. Transcripts and session artifacts do not survive.
So an audit whose output stayed in the harness is an audit that was paid for and not
banked, and the failure is invisible at the time — the workflow *succeeded*, it reported
findings, and the orchestrator read them. Nothing signals that they evaporated.

WHY A HOOK RATHER THAN A LINE IN THE BRIEF
------------------------------------------
Workflow scripts have **no filesystem access** — they cannot write the repo themselves.
So the obligation necessarily lands on the orchestrator, after the workflow returns,
which is exactly the kind of "remember to do the thing afterwards" that prose does not
enforce. Same reasoning as requirement_before_mechanism.py: a rule satisfiable by
*saying* you followed it selects for the appearance of the behaviour.

WHAT IT DOES
------------
On Stop, if the turn used the Workflow tool but wrote/edited **no file inside a git
repo**, block once and name the rule.

Deliberately narrow, because a guard that cries wolf gets disabled and takes its true
positives with it:
  * only the ``Workflow`` tool counts — a plain ``Agent`` subagent is exempt, since
    delegating a lookup is not the same as commissioning repo-work;
  * a write anywhere under a known repo root satisfies it — docs, reviews, TODO, source;
  * scratchpad/temp writes do NOT satisfy it (that is the failure mode itself);
  * fires at most ONCE per turn (honours stop_hook_active);
  * ``workflow-output:ok`` anywhere in the turn is the explicit escape hatch, for the
    genuine case where a workflow answered a throwaway question with no durable product.
"""
import json
import os
import re
import sys


def _record(trigger: str, transcript_path, extra: dict) -> None:
    """Bank this fire to ~/.claude/hook-events.jsonl. Best-effort, never raises.

    Wired 2026-07-22 alongside the other three guards. Defined before its call site
    (run-4 lesson: instrumenting call-sites before the helper NameErrors on every fire
    in between).
    """
    try:
        hooks_dir = os.path.dirname(os.path.abspath(__file__))
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        from hook_log import record
        record("workflow_output_to_repo", trigger=trigger,
               transcript_path=transcript_path, extra=extra)
    except Exception:
        pass


# A write under one of these counts as "in the repo". Kept as path fragments so it works
# regardless of drive letter or checkout location.
#
# WHY THIS IS CONFIGURATION AND NOT A LITERAL IN THIS FILE
# -------------------------------------------------------
# The list is inherently machine-specific: it is *which repos this operator does durable
# work in*, which differs per box and names private projects. Hardcoding it here would
# either leak those names into a public repo or, if scrubbed, leave the hook matching
# nothing -- and a hook that matches nothing does not fail loudly, it silently stops
# recognising real repo writes and blocks every workflow turn instead. That silent
# mis-fire is the exact class of failure the rest of this file argues against.
#
# So: the MECHANISM ships here, the DATA lives next to the machine that knows it.
# One fragment per line in the config file, blank lines and `#` comments ignored.
# See workflow-output-repos.conf.example.
CONF_ENV = "WORKFLOW_OUTPUT_REPOS_CONF"        # override the config path (tests use this)
CONF_DEFAULT = "~/.claude/workflow-output-repos.conf"

# Used when no config file exists. Deliberately BROAD rather than empty: an empty list
# means "no write ever counts", which turns the guard into a blocker on every workflow
# turn. A checkout-directory fragment keeps it roughly right on an unconfigured box, and
# the operator narrows it by writing the config file.
FALLBACK_FRAGMENTS = ("/github/",)


def load_repo_fragments(conf_path: str | None = None) -> tuple[str, ...]:
    """Read durable-repo path fragments from machine-local config.

    Falls back to FALLBACK_FRAGMENTS when the file is absent or contains no entries,
    so an unconfigured machine still gets a working hook rather than a silent one.
    """
    path = conf_path or os.environ.get(CONF_ENV) or os.path.expanduser(CONF_DEFAULT)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return FALLBACK_FRAGMENTS
    frags = tuple(
        s.lower().replace("\\", "/")
        for s in (line.strip() for line in lines)
        if s and not s.startswith("#")
    )
    return frags or FALLBACK_FRAGMENTS


REPO_FRAGMENTS = load_repo_fragments()

# These never satisfy the rule even though they are real writes -- writing the findings
# to a temp file is precisely the thing that lost the audit.
NON_DURABLE = ("/scratchpad/", "\\scratchpad\\", "/temp/", "\\temp\\", "/tmp/", "\\tmp\\",
               "/appdata/local/temp/", "\\appdata\\local\\temp\\")

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
OVERRIDE = re.compile(r"workflow-output:\s*ok", re.I)


def in_repo(path: str) -> bool:
    if not path:
        return False
    low = path.lower().replace("\\", "/")
    if any(frag.replace("\\", "/") in low for frag in NON_DURABLE):
        return False
    return any(frag in low for frag in REPO_FRAGMENTS)


def current_turn(transcript_path: str):
    """(assistant_text, used_workflow, repo_paths_written) since the last real user msg."""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return "", False, []

    start = 0
    for i in range(len(entries) - 1, -1, -1):
        e = entries[i]
        if e.get("type") == "user":
            content = (e.get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                start = i
                break

    text_parts, used_workflow, written = [], False, []
    for e in entries[start:]:
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                name = block.get("name")
                if name == "Workflow":
                    used_workflow = True
                elif name in EDIT_TOOLS:
                    path = (block.get("input") or {}).get("file_path") or ""
                    if in_repo(path):
                        written.append(path)
    return "\n".join(text_parts), used_workflow, written


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed payload

    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    text, used_workflow, written = current_turn(transcript)
    if not used_workflow or written:
        return 0
    if OVERRIDE.search(text):
        return 0

    reason = (
        "This turn ran a Workflow but wrote nothing into a repo.\n\n"
        "RULE (Brad, 2026-07-20): workflows output repo-work to the repo.\n\n"
        "A run is a Prestige cycle -- the next agent carries over ONLY what is on disk "
        "in the repo. Transcripts and session artifacts do not survive. A 3.3M-token "
        "audit on 2026-07-19 found 19 real defects and banked none of them; they lived "
        "only in ~/.claude/projects/.../workflows/ and were recovered by luck one "
        "session later.\n\n"
        "Do one of these before finishing:\n"
        "  - write the workflow's product to the repo (docs/reviews/<date>-<topic>.md "
        "for findings, docs/TODO.md for work items, or the source it changed);\n"
        "  - if the workflow answered a throwaway question with no durable product, say "
        "'workflow-output:ok' and why.\n\n"
        "A scratchpad or temp-file write does NOT count -- that is the failure mode."
    )
    _record("workflow-no-write", transcript, {"event": "fired"})
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

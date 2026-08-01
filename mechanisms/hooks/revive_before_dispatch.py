#!/usr/bin/env python3
"""Agent guard — do not dispatch a FRESH agent of a type you already have this session.

THE FAILURE THIS PREVENTS, measured 2026-08-01. One conductor run made **8 fresh `Agent` calls and
exactly 1 `SendMessage`**. Three of the eight were the same SME type, sequential, minutes apart —
decode coredumps, then build+OTA the fix, then merge the branches. Each re-primed from zero: the
repo CLAUDE.md, the orientation gate, the same build gotchas. Worse than the tokens: a revived
agent would have *known* it had just built the image the next lot had to flash, and that
connection had to be re-derived by the conductor instead.

The operator's framing, verbatim: *"A bigger factor for usage though is simply spawning 8 new
agent sessions to do firmware work over the course of a single conductor run, and paying for
initializing each one, let alone paying for them to make similar mistakes and re-deriving the same
lessons."* And: *"the conductor should re-use agents like SMEs."*

WHY A GUARD AND NOT A RULE. The rule already existed in the brief, added the same day, and was
violated in the same run by an agent that had read it. It is Voluntary class and it reads as an
optimisation — and optimisations lose to whatever is in front of you. The `Agent` tool is what you
reach for when you have a NEW TASK; the revive path requires remembering that a previous agent's
context is an asset. This fires at the moment of dispatch, on an agent that never read any rule.

CONTRACT
  - PostToolUse on Agent records (subagent_type, agentId, description) for this session. This half
    MUST be post-tool: the agentId exists only in the RESULT, never in the input.
  - PreToolUse on Agent denies a fresh dispatch when a same-type agent is already on record, and
    prints the exact `SendMessage` replacement — a block that only says "don't" makes you guess.
  - ESCAPE HATCH, non-negotiable and logged: put `cold-required: <reason>` in the prompt. An
    adversarial verify genuinely needs a cold agent — a revived one is contaminated by its own
    earlier conclusion — and a guard with no legitimate escape gets disabled wholesale, taking its
    true positives with it.
  - The deny does NOT claim revival is always right. Revival re-reads the agent's whole transcript
    and was measured at 194,017 tokens for a one-word reply from a context-heavy agent. The
    discriminator is *do I want what it knows*, and the deny message says so, because the guard
    cannot know the answer and must not pretend to.
  - Per-session state only. Cross-session revival was measured impossible (the resume registry is
    per-session), so a stale registry from a previous session must never produce a block.
  - FAIL-OPEN on any internal error, unreadable state, or unexpected payload. A bug here must
    never block a dispatch.

INSTALL (PreToolUse *and* PostToolUse, matcher "Agent"), in ~/.claude/settings.json:

    {"matcher": "Agent", "hooks": [{"type": "command", "timeout": 10,
      "command": "py -3 -c \\"import runpy,os;runpy.run_path(os.path.expanduser('~/.claude/hooks/revive_before_dispatch.py'),run_name='__main__')\\""}]}

Both halves are required. With only the Pre half the registry is always empty and the guard never
fires — silently, which is the worst outcome for a guard.
"""
import json
import os
import re
import sys
import time

STATE_DIR = os.path.expanduser("~/.claude/state")
LOG = os.path.join(STATE_DIR, "revive-guard.log")
ESCAPE = re.compile(r"cold-required:\s*(\S.*)", re.IGNORECASE)
AGENTID = re.compile(r"\b(a[0-9a-f]{12,})\b")


def allow():
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    return os.path.join(STATE_DIR, f"agent-registry-{safe}.json")


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path, data):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def _log(line):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {line}\n")
    except OSError:
        pass


def agent_id_from(response):
    """The agentId lives only in the tool RESULT, and its shape is not guaranteed."""
    if isinstance(response, dict):
        for key in ("agentId", "agent_id"):
            val = response.get(key)
            if isinstance(val, str) and val:
                return val
    try:
        blob = response if isinstance(response, str) else json.dumps(response)
    except (TypeError, ValueError):
        return None
    match = AGENTID.search(blob or "")
    return match.group(1) if match else None


def handle_post(payload):
    """Record the agent we just dispatched. Never blocks anything."""
    tool_input = payload.get("tool_input") or {}
    subagent = tool_input.get("subagent_type") or "general-purpose"
    agent_id = agent_id_from(payload.get("tool_response"))
    if not agent_id:
        return allow()
    path = _state_path(payload.get("session_id"))
    state = _load(path)
    entries = state.setdefault(subagent, [])
    if not any(e.get("agentId") == agent_id for e in entries):
        entries.append({
            "agentId": agent_id,
            "description": (tool_input.get("description") or "")[:120],
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        _save(path, state)
    allow()


def block_reason(subagent, prior):
    """The deny text. Split out so a test can assert what it names."""
    last = prior[-1]
    others = ""
    if len(prior) > 1:
        others = "\n  (also this session: " + ", ".join(
            f"{p['agentId']} \"{p['description'][:40]}\"" for p in prior[:-1]
        ) + ")"
    return (
        f"You already have a '{subagent}' agent this session. Reuse it like an SME rather than "
        f"paying to prime a new one.\n\n"
        f"  agentId     {last['agentId']}\n"
        f"  dispatched  {last['at']}  \"{last['description']}\"{others}\n\n"
        f"REPLACEMENT — resume it with its context intact:\n"
        f"  SendMessage(to: '{last['agentId']}', summary: '<5-10 word recap>', "
        f"message: '<your new task>')\n\n"
        f"Two cases where a FRESH agent is genuinely right, and this guard cannot tell which you "
        f"are in:\n"
        f"  1. An adversarial verify. A revived agent is contaminated by its own earlier "
        f"conclusion.\n"
        f"  2. A small UNRELATED task when that agent is context-heavy. Revival re-reads its whole "
        f"transcript — measured at 194,017 tokens for a one-word reply — so a fresh agent can be "
        f"cheaper. The test is 'do I want what it knows', not 'does an agent of this type exist'.\n\n"
        f"If one of those applies, put `cold-required: <your reason>` in the prompt and re-issue. "
        f"It is logged, not silent.\n\n"
        f"If that agent may still be RUNNING, prefer waiting for its completion notification over "
        f"either path — `TaskStop` on an id you already believe is dead doubles as a census of "
        f"what is live."
    )


def handle_pre(payload):
    tool_input = payload.get("tool_input") or {}
    subagent = tool_input.get("subagent_type") or "general-purpose"
    prompt = tool_input.get("prompt") or ""

    escape = ESCAPE.search(prompt)
    if escape:
        _log(f"ESCAPE {subagent}: {escape.group(1)[:160]}")
        return allow()

    prior = _load(_state_path(payload.get("session_id"))).get(subagent) or []
    if not prior:
        return allow()

    _log(f"BLOCK {subagent}: {len(prior)} prior, newest {prior[-1]['agentId']}")
    deny(block_reason(subagent, prior))


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return allow()
    try:
        if (payload.get("tool_name") or "") != "Agent":
            return allow()
        event = payload.get("hook_event_name") or ""
        if event == "PostToolUse":
            return handle_post(payload)
        if event == "PreToolUse":
            return handle_pre(payload)
        return allow()
    except Exception:  # noqa: BLE001 — fail-open is the contract
        return allow()


if __name__ == "__main__":
    main()

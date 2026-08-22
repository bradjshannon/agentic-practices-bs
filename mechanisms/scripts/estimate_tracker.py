#!/usr/bin/env python3
"""Track an agent's own wall-clock estimate against measured wall-clock reality.

WHY THIS EXISTS (the operator, 2026-08-03): "Agents often claim work will take X hours/days, which is
always based on human prediction heuristics that don't apply to agentic work. I want to measure
agents' estimating accuracy, for fun." Not a safety control -- a measurement instrument. It must
still be a hook and not a rule, for the same reason every other control here is: an agent asked to
"estimate, then compare" will happily narrate having done so without the number ever being
recorded before the outcome was known, which is worthless for calibration research.

WHAT COUNTS AS "A CHUNK OF WORK": every dispatch through the `Agent` tool. The operator left the boundary
to my judgment. A subagent dispatch is the natural unit because it is the one place this harness
already measures real wall-clock duration itself (`duration_ms` in the tool result and in the
async completion notification) -- ungameable, since the agent being measured never produces that
number. An inline turn the top-level model does itself has no equivalent structural timer, so it
is deliberately out of scope here (see the docstring in the brief discussion this was built from).

THE THREE-PART CONTRACT, one file, three hook roles:

  1. PreToolUse(Agent): require an `ESTIMATE: <duration>` line in the prompt before the dispatch
     is allowed. Denies with the exact format otherwise. Escape hatch: `ESTIMATE: skip <reason>`
     for genuinely unbounded/exploratory work -- logged, not silent, same shape as every other
     escape hatch in this directory.
  2. PostToolUse(Agent): the agentId exists only in the tool RESULT, never the input (same fact
     revive_before_dispatch.py already documents). Links the just-created pending estimate to the
     real agentId. If the tool result ALREADY carries duration usage (a foreground/non-background
     call returns synchronously), reconciles immediately instead of waiting for step 3.
  3. Stop-hook check (registered in stop_gate.py's CHECKS list): scans this turn's transcript for
     `<task-notification>` blocks -- the async completion signal for a BACKGROUND dispatch -- and
     reconciles any pending estimate whose agentId just reported in. NEVER blocks the turn; this
     is pure bookkeeping riding along on a hook that already runs every turn. A crash here must
     cost nothing, so every code path fails open.

STORAGE
  Pending/linked-but-not-yet-reconciled records: ~/.claude/state/estimate-registry-<session>.json
  (per-session, like revive_before_dispatch.py's registry).
  Finished comparisons: ~/.claude/state/estimate-results.jsonl (append-only, cross-session --
  this is the actual dataset the operator wants to look at).

INSTALL
  PreToolUse AND PostToolUse, matcher "Agent" (same two-half shape as revive_before_dispatch.py --
  with only the Pre half the registry is always empty and nothing ever reconciles):

    {"matcher": "Agent", "hooks": [{"type": "command", "timeout": 10,
      "command": "py -3 -c \\"import runpy,os;runpy.run_path(os.path.expanduser('~/.claude/hooks/estimate_tracker.py'),run_name='__main__')\\""}]}

  Plus one line in stop_gate.py's CHECKS list: "estimate_tracker.py".
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

def _state_dir():
    # Env override for tests: a module-level constant can't be patched after runpy.run_path()
    # returns, since that returns a COPY of the module's globals, not the dict the already-defined
    # functions actually close over (verified empirically -- see estimate_tracker_test.py).
    return os.environ.get("ESTIMATE_TRACKER_STATE_DIR") or os.path.expanduser("~/.claude/state")


def _results_path():
    return os.path.join(_state_dir(), "estimate-results.jsonl")


def _log_path():
    return os.path.join(_state_dir(), "estimate-tracker.log")

ESTIMATE = re.compile(r"ESTIMATE:\s*([^\n]+)", re.IGNORECASE)
# Same match, but greedy enough to eat the line (and one trailing newline) for redaction --
# kept separate from ESTIMATE above because that one is used for *parsing* the value (group(1)
# must stay tight to the value) and this one is used for *deleting* the line wholesale.
ESTIMATE_LINE = re.compile(r"^[ \t]*ESTIMATE:[^\n]*\n?", re.IGNORECASE | re.MULTILINE)
SKIP = re.compile(r"^\s*skip\b", re.IGNORECASE)
DURATION = re.compile(
    r"([\d.]+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|"
    r"h|hr|hrs|hour|hours|d|day|days)\b",
    re.IGNORECASE,
)
UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}
AGENTID = re.compile(r"\b(a[0-9a-f]{12,})\b")
NOTIFICATION = re.compile(
    r"<task-id>\s*([a-z0-9]+)\s*</task-id>.*?<duration_ms>\s*(\d+)\s*</duration_ms>",
    re.IGNORECASE | re.DOTALL,
)


def _log(line):
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {line}\n")
    except OSError:
        pass


def parse_estimate(prompt: str):
    """Return (seconds, raw_text) or (None, raw_text) for a skip, or (None, None) if absent."""
    m = ESTIMATE.search(prompt or "")
    if not m:
        return None, None
    raw = m.group(1).strip()
    if SKIP.match(raw):
        return None, raw
    dm = DURATION.search(raw)
    if not dm:
        return None, raw
    value = float(dm.group(1))
    unit = dm.group(2).lower()
    return value * UNIT_SECONDS[unit], raw


def _state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    return os.path.join(_state_dir(), f"estimate-registry-{safe}.json")


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {"pending": [], "linked": []}
    except (OSError, ValueError):
        return {"pending": [], "linked": []}


def _save(path, data):
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def _append_result(record):
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_results_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def allow():
    sys.exit(0)


def allow_redacted(tool_input, prompt):
    """Allow the dispatch, but with the ESTIMATE line stripped from what the SUBAGENT actually
    receives. The estimate is tracking metadata for comparing against `duration_ms` afterward --
    it has no business being part of the subagent's own instructions, and leaving it in has a
    measured failure mode: an agent reading its own budget as a target and self-terminating
    against it well short of the work being done (caught live 2026-08-08 -- a thread-audit agent
    stopped at 13/89 cards, ~32 of its ~120 allotted minutes used, and reported "ran out of time"
    against the 2h estimate it should never have seen). Requires a real terminating condition (the
    task's own scope), not a clock it was never supposed to be racing.
    """
    new_input = dict(tool_input)
    new_input["prompt"] = ESTIMATE_LINE.sub("", prompt, count=1)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": new_input,
        }
    }))
    sys.exit(0)


def deny(reason):
    # Bank the block BEFORE emitting it. A blocking hook that leaves no trace cannot be asked
    # "how often do you fire, and are you earning your place" -- measured 2026-08-13, 5 of 5
    # subagent dispatches in one fan-out were blocked here and none appeared in hook-events.jsonl.
    # Never raises and never alters the verdict below.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("estimate_tracker", trigger=str(reason)[:120],
                        extra={"decision": "deny"})
    except Exception:
        pass
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


DENY_TEXT = (
    "Bounded work dispatched through `Agent` needs an upfront wall-clock estimate, recorded "
    "BEFORE the work happens -- so it can be compared to reality afterward without the "
    "estimate being revised in hindsight. Put it in the `description` field, NOT in the "
    "prompt -- it is tracking metadata, not something the subagent should read:\n\n"
    "  description: \"fix login redirect ESTIMATE: 20m\"\n"
    "  units: s / m / h / d   e.g. ESTIMATE: 90s / ESTIMATE: 2h\n\n"
    "If this dispatch genuinely isn't bounded work (a quick lookup, exploratory research with "
    "no natural finish line), use the escape hatch instead -- logged, not silent:\n\n"
    "  description: \"survey the codebase ESTIMATE: skip <one-line reason>\"\n"
)


def handle_pre(payload):
    tool_input = payload.get("tool_input") or {}
    prompt = tool_input.get("prompt") or ""
    description = tool_input.get("description") or ""

    # `description` is the carrier, checked FIRST. It is a short label the harness records and
    # never delivers to the subagent as instructions, so an estimate written there cannot leak
    # into the brief at all -- which is stronger than redacting it out of the prompt afterwards,
    # because the prompt is also what a human reads in the transcript. The prompt fallback below
    # stays for back-compat and is redacted on the way through.
    seconds, raw = parse_estimate(description)
    from_prompt = False
    if raw is None:
        seconds, raw = parse_estimate(prompt)
        from_prompt = raw is not None

    if raw is None:
        return deny(DENY_TEXT)
    if seconds is None:
        # explicit skip
        _log(f"SKIP: {raw[:160]}")
        return allow_redacted(tool_input, prompt) if from_prompt else allow()

    path = _state_path(payload.get("session_id"))
    state = _load(path)
    state.setdefault("pending", []).append({
        "description": (tool_input.get("description") or "")[:120],
        "estimate_raw": raw,
        "estimate_seconds": seconds,
        "subagent_type": tool_input.get("subagent_type") or "general-purpose",
        "dispatched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _save(path, state)
    if from_prompt:
        allow_redacted(tool_input, prompt)
    allow()


def agent_id_from(response):
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


def usage_duration_ms(response):
    """A foreground (non-backgrounded) Agent call may return usage synchronously. Best-effort."""
    if not isinstance(response, dict):
        return None
    for key in ("duration_ms", "durationMs"):
        val = response.get(key)
        if isinstance(val, (int, float)):
            return val
    usage = response.get("usage")
    if isinstance(usage, dict):
        for key in ("duration_ms", "durationMs"):
            val = usage.get(key)
            if isinstance(val, (int, float)):
                return val
    return None


def _reconcile(state, entry, agent_id, actual_ms, path):
    result = {
        "agentId": agent_id,
        "subagent_type": entry.get("subagent_type"),
        "description": entry.get("description"),
        "estimate_raw": entry.get("estimate_raw"),
        "estimate_seconds": entry.get("estimate_seconds"),
        "dispatched_at": entry.get("dispatched_at"),
        "actual_seconds": actual_ms / 1000.0,
        "delta_seconds": actual_ms / 1000.0 - entry.get("estimate_seconds", 0),
        "ratio_actual_over_estimate": (
            (actual_ms / 1000.0) / entry["estimate_seconds"]
            if entry.get("estimate_seconds") else None
        ),
        "reconciled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _append_result(result)
    state.setdefault("reconciled_ids", []).append(agent_id)
    _save(path, state)
    _log(f"RECONCILED {agent_id}: est={entry.get('estimate_raw')} actual={actual_ms}ms")


def handle_post(payload):
    """Link the dispatch to its agentId; reconcile immediately if usage is already available."""
    tool_input = payload.get("tool_input") or {}
    response = payload.get("tool_response")
    agent_id = agent_id_from(response)
    if not agent_id:
        return allow()

    path = _state_path(payload.get("session_id"))
    state = _load(path)
    pending = state.get("pending") or []
    description = (tool_input.get("description") or "")[:120]
    subagent_type = tool_input.get("subagent_type") or "general-purpose"

    # Match the most recent pending entry with the same (description, subagent_type) --
    # dispatches are issued sequentially by one model, so this is reliable without needing a
    # shared correlation id. Matching on description ALONE collided when two dispatches (e.g. a
    # revive-vs-fresh-agent retry of the same lot) reused the same description text under a
    # different subagent_type -- one entry then silently orphaned the other. Measured 2026-08-22:
    # a reconciliation pass found several of the 551 orphaned entries traced to exactly this.
    idx = None
    for i in range(len(pending) - 1, -1, -1):
        if pending[i].get("description") == description and (
            pending[i].get("subagent_type") == subagent_type
        ):
            idx = i
            break
    if idx is None:
        # Fall back to description-only, for entries recorded before subagent_type was tracked
        # (or the rare cross-type dispatch of literally the same description) -- fail toward the
        # old behavior rather than orphaning outright.
        for i in range(len(pending) - 1, -1, -1):
            if pending[i].get("description") == description:
                idx = i
                break
    if idx is None:
        return allow()  # no ESTIMATE was recorded for this dispatch (shouldn't happen; fail open)

    entry = pending.pop(idx)
    entry["agentId"] = agent_id
    _save(path, {**state, "pending": pending})

    actual_ms = usage_duration_ms(response)
    if actual_ms is not None:
        _reconcile(state, entry, agent_id, actual_ms, path)
    else:
        # Background dispatch: no duration yet. Park it linked-but-unreconciled; the Stop-hook
        # check below finishes this when the async completion notification arrives.
        state = _load(path)
        state.setdefault("linked", []).append(entry)
        _save(path, state)
    allow()


def _read_transcript_text(transcript_path, max_lines=200):
    """Best-effort flatten of recent transcript lines to searchable text. Never raises."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    chunks = []
    for line in lines[-max_lines:]:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        content = (obj.get("message") or {}).get("content") if isinstance(obj, dict) else None
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content") or ""
                    if isinstance(text, str):
                        chunks.append(text)
    return "\n".join(chunks)


def check_stop(payload):
    """Called from stop_gate.py's aggregator (and standalone). Never blocks -- returns nothing."""
    session_id = payload.get("session_id")
    path = _state_path(session_id)
    state = _load(path)
    linked = state.get("linked") or []
    if not linked:
        return
    reconciled_ids = set(state.get("reconciled_ids") or [])
    text = _read_transcript_text(payload.get("transcript_path"))
    if not text:
        return
    found = {aid: int(dur) for aid, dur in NOTIFICATION.findall(text)}
    remaining = []
    for entry in linked:
        aid = entry.get("agentId")
        if aid in found and aid not in reconciled_ids:
            state = _load(path)  # re-load in case _reconcile below already mutated it
            _reconcile(state, entry, aid, found[aid], path)
        else:
            remaining.append(entry)
    if len(remaining) != len(linked):
        state = _load(path)
        state["linked"] = remaining
        _save(path, state)


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return allow()
    # So deny(), which is not given the payload, can still resolve the session.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.bind(payload)
    except Exception:
        pass
    try:
        event = payload.get("hook_event_name") or ""
        if event == "Stop":
            check_stop(payload)
            return allow()
        if (payload.get("tool_name") or "") != "Agent":
            return allow()
        if event == "PostToolUse":
            return handle_post(payload)
        if event == "PreToolUse":
            return handle_pre(payload)
        return allow()
    except Exception:  # noqa: BLE001 -- fail-open is the contract; this is a metrics toy, not a
        # safety control, so a bug here must never cost a turn or a dispatch.
        return allow()


if __name__ == "__main__":
    main()

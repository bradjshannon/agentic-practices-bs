#!/usr/bin/env python3
"""Shared append-only log of hook FIRES — the raw data for measuring hook effectiveness.

The operator, 2026-07-20: every hook fire that is valid should measure itself and surface whether it was
necessary. This is the collection layer. It records ONE thing: that a hook fired, on what trigger,
in which session. It records NO verdict — a hook that logged "I was necessary" would be a tool
asserting its own value, the exact misleading-report failure the whole philosophy warns against.

Validity ("was this fire necessary / a true positive") is NOT knowable at fire time — it depends on
what the agent does NEXT (rewrite the command = the guard was right; override the block = suspect).
So validity is computed by a SEPARATE pass (hook_rollup.py) that correlates each fire against the
following action. This module only banks the fire.

One JSONL line per fire, appended to ~/.claude/hook-events.jsonl (or wherever ``HOOK_LOG_PATH``
points — every TEST must set it to a temp file; see log_path()):
  {"ts": "...", "hook": "output_budget", "session": "<id>", "trigger": "<short snippet>"}

Never raises: a logging failure must not break the hook it instruments (the hook's job is more
important than the metric). All errors are swallowed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

DEFAULT_LOG_PATH = os.path.expanduser("~/.claude/hook-events.jsonl")

# The live instrument. Kept as a module attribute so an in-process test can monkeypatch it
# (tool_output_volume_test.py does), and so callers can read where the log went.
LOG_PATH = DEFAULT_LOG_PATH


def log_path() -> str:
    """Where record() appends. ``HOOK_LOG_PATH`` wins; unset, it is the live log — byte-identical
    to the old hardcoded behaviour.

    THIS EXISTS BECAUSE THE INSTRUMENT WAS EATING ITS OWN TESTS (measured 2026-08-14). With no
    override, every hook test that reaches a ``record()`` call appended to the REAL
    ~/.claude/hook-events.jsonl — the one file that says whether a hook works, and the corpus
    hook_rollup.py and the 2026-08-14 rules triage both read. Measured that day: 8 of 21 test
    files, 32 synthetic rows per full suite run, plus 100 historical rows still carrying
    repo_doc_guard_test's ``aTEST1``/``aTEST3`` fixture ids — 15% of that hook's denies.
    A test that pollutes real state makes the next real measurement a lie; brief_shape_guard.py
    learned this first (``BRIEF_SHAPE_GUARD_STATE_DIR``), hook_log did not get the same treatment
    until now.

    The env var is re-read on every call, NOT captured at import. Import-time capture is the
    silent-failure shape: a test that sets the variable after some other hook module has already
    imported hook_log would go on polluting with nothing saying so.

    ANY NEW HOOK TEST MUST SET ``HOOK_LOG_PATH`` TO A TEMP FILE. There is no runner to enforce it
    — the estate's hook tests are standalone scripts. Re-measure with the line-count probe (run
    each test, diff ``wc -l`` on the live log) rather than by reading sources: reading is what
    missed this for the instrument's whole life.
    """
    return os.environ.get("HOOK_LOG_PATH") or LOG_PATH


def _session_from_transcript(transcript_path: str | None) -> str | None:
    """The session id is the transcript filename stem (…/<session-id>.jsonl)."""
    if not transcript_path:
        return None
    base = os.path.basename(transcript_path)
    return base[:-6] if base.endswith(".jsonl") else base


# The payload of the fire currently being handled, stashed by bind() so that a record() call
# made deep in a hook — typically inside a `deny()` helper that was never given the payload —
# can still resolve the session. Without this, a blocking hook logs `session: null` and
# hook_rollup.py can classify none of its fires: measured 2026-08-13, three guards accounted for
# 1,786 unclassifiable rows between them. Process-global is safe because a hook process handles
# exactly one fire and then exits.
_BOUND_PAYLOAD: dict = {}


def bind(payload: object) -> None:
    """Remember this fire's payload so a later record() can derive the session from it.

    Call once, right after the hook parses stdin. Never raises: a hook must not die because its
    telemetry could not be set up.
    """
    global _BOUND_PAYLOAD
    try:
        _BOUND_PAYLOAD = payload if isinstance(payload, dict) else {}
    except Exception:
        _BOUND_PAYLOAD = {}


def record(hook: str, *, trigger: str = "", transcript_path: str | None = None,
           session: str | None = None, extra: dict | None = None,
           payload: object = None) -> None:
    """Append one fire event. Best-effort; never raises.

    ``trigger`` is a SHORT human-readable snippet of what set the hook off (a truncated command,
    a char count) — enough to eyeball later, not the whole payload.

    The session is resolved from the first of: an explicit ``session``; an explicit
    ``transcript_path``; the ``payload`` passed here; the payload stashed by ``bind()``; and
    finally the payload's own ``session_id``.

    THE LAST FALLBACK IS NOT REDUNDANT (measured 2026-08-14). ``transcript_path`` is absent from
    the PreToolUse payload some hooks receive, and this function used to read ONLY that key — so
    a hook that correctly passed its whole payload still logged ``session: null``. That, not a
    missing ``bind()``, is what made 1,862 of 23,127 rows unattributable, 1,651 of them
    ``lying_command_guard`` — the guard whose 943 genuine ``# guard:ok`` overrides sit in the
    transcripts unmeasurable. ``agent_id`` is carried for the same reason: the acting subagent
    has its own transcript (``<proj>/<session>/subagents/agent-<id>.jsonl``) and hook_rollup.py
    now classifies against THAT, not the parent's.

    Telemetry only: nothing here can change a hook's verdict.
    """
    try:
        src = payload if isinstance(payload, dict) else _BOUND_PAYLOAD
        if not isinstance(src, dict):
            src = {}
        if not transcript_path:
            transcript_path = src.get("transcript_path")
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hook": hook,
            "session": (session or _session_from_transcript(transcript_path)
                        or src.get("session_id") or None),
            "trigger": (trigger or "")[:200],
        }
        if src.get("agent_id"):
            row["agent_id"] = src["agent_id"]
        if extra:
            # A caller's explicit extra wins, EXCEPT that a None must not erase an id we just
            # resolved (subagent_background_wait_guard passes extra={"agent_id": None} when the
            # payload had none).
            row.update({k: v for k, v in extra.items() if v is not None or k not in row})
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass  # a dead metric must never take a live hook down with it


def describe_call(payload: object) -> str:
    """Short human-readable description of the tool call a guard was adjudicating, e.g.
    ``Bash: git push origin main``. Best-effort; never raises. Used by ``record_fail_open`` so
    a COULD-NOT-ADJUDICATE row names what was in flight when the guard crashed, not just that
    it crashed.
    """
    try:
        src = payload if isinstance(payload, dict) else _BOUND_PAYLOAD
        if not isinstance(src, dict):
            return ""
        tool = src.get("tool_name") or src.get("hook_event_name") or ""
        tin = src.get("tool_input") or {}
        detail = (tin.get("command") or tin.get("file_path") or tin.get("notebook_path")
                  or tin.get("description") or tin.get("prompt") or "")
        text = f"{tool}: {detail}" if detail else str(tool)
        return text[:150]
    except Exception:
        return ""


def record_fail_open(hook: str, exc: BaseException, *, payload: object = None,
                      transcript_path: str | None = None, session: str | None = None,
                      tool_call: str | None = None) -> None:
    """Bank a COULD-NOT-ADJUDICATE row: a guard's fail-open catch fired, so the call was
    ALLOWED not because the guard checked it and approved, but because the guard itself broke.

    This is a THIRD state, not a second flavour of allow. Without it, a crashed guard and an
    absent guard are indistinguishable from outside -- both look like silence. Fail-open stays
    the contract (never blocks on a guard's own bug); this only makes the crash observable.

    Never raises -- delegates to ``record()``, which never raises. Call this from INSIDE the
    fail-open except block, before the guard exits 0 / allows.
    """
    try:
        name = type(exc).__name__
        call = tool_call if tool_call is not None else describe_call(payload)
        trigger = f"{name}: {exc}"[:200]
        record(hook, trigger=trigger, transcript_path=transcript_path, session=session,
               payload=payload,
               extra={"decision": "could_not_adjudicate", "exception_type": name,
                      "tool_call": call})
    except Exception:
        pass

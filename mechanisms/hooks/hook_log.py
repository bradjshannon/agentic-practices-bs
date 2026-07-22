#!/usr/bin/env python3
"""Shared append-only log of hook FIRES — the raw data for measuring hook effectiveness.

Brad, 2026-07-20: every hook fire that is valid should measure itself and surface whether it was
necessary. This is the collection layer. It records ONE thing: that a hook fired, on what trigger,
in which session. It records NO verdict — a hook that logged "I was necessary" would be a tool
asserting its own value, the exact misleading-report failure the whole philosophy warns against.

Validity ("was this fire necessary / a true positive") is NOT knowable at fire time — it depends on
what the agent does NEXT (rewrite the command = the guard was right; override the block = suspect).
So validity is computed by a SEPARATE pass (hook_rollup.py) that correlates each fire against the
following action. This module only banks the fire.

One JSONL line per fire, appended to ~/.claude/hook-events.jsonl:
  {"ts": "...", "hook": "output_budget", "session": "<id>", "trigger": "<short snippet>"}

Never raises: a logging failure must not break the hook it instruments (the hook's job is more
important than the metric). All errors are swallowed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hook-events.jsonl")


def _session_from_transcript(transcript_path: str | None) -> str | None:
    """The session id is the transcript filename stem (…/<session-id>.jsonl)."""
    if not transcript_path:
        return None
    base = os.path.basename(transcript_path)
    return base[:-6] if base.endswith(".jsonl") else base


def record(hook: str, *, trigger: str = "", transcript_path: str | None = None,
           session: str | None = None, extra: dict | None = None) -> None:
    """Append one fire event. Best-effort; never raises.

    ``trigger`` is a SHORT human-readable snippet of what set the hook off (a truncated command,
    a char count) — enough to eyeball later, not the whole payload.
    """
    try:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hook": hook,
            "session": session or _session_from_transcript(transcript_path),
            "trigger": (trigger or "")[:200],
        }
        if extra:
            row.update(extra)
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass  # a dead metric must never take a live hook down with it

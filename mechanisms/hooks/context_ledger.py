#!/usr/bin/env python3
"""Stop check: one repeated string eating a large share of the context window.

WHY THIS EXISTS
---------------
An aggregate context percentage can never indict a component. On session 28d7e184 the pacer
printed "context 76% used" while **22% of the window was a single string** — 3,069 byte-identical
copies of a Windows "Python was not found" stub, emitted by a misconfigured plugin hook, ~221k
tokens. Every existing instrument read the total and called it fine; the leak was found only by a
3.4M-token cold-read workflow, by luck.

This watches BYTES THAT ACTUALLY ENTERED THE WINDOW, bucketed by normalized string identity, and
objects when any one normalized string crosses BOTH a count and a byte floor. It cannot be
satisfied by saying anything — it reads the transcript the model was actually fed.

DESIGN
------
* Fires at most ONCE per (session, offending string): a leak is present every turn thereafter, and
  re-objecting each turn is the noise that gets a gate disabled. A tiny per-session state file
  records what has already been reported.
* Count floor (>=50 identical copies) distinguishes machine chrome from a legitimate large Read or
  a long pytest tail, which are one copy. Byte floor (>=60 KB) keeps it from firing on 50 tiny
  repeats that cost nothing. BOTH must hold.
* FAIL-OPEN everywhere: any error prints nothing and the turn proceeds. A detector that can hold a
  turn hostage on its own bug is worse than the leak it hunts.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

COUNT_FLOOR = 50           # identical copies before it is "chrome", not content
BYTE_FLOOR = 60_000        # ~15k tokens; below this the repetition is not worth an interrupt
SIG_LEN = 400              # chars of normalized text used as the bucket key / shown to the human
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state", "context_ledger")


def _collect_strings(obj, out: list[str]) -> None:
    """Every string value anywhere in the entry — the text the window actually carried."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, out)


def _entry_text(entry: dict) -> str:
    parts: list[str] = []
    _collect_strings(entry.get("message") or entry, parts)
    return "\n".join(parts)


def _norm(s: str) -> str:
    return " ".join(s.split())


def _state_path(session: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session or "nosession"))[:80]
    return os.path.join(STATE_DIR, f"{safe}.json")


def _seen(session: str) -> set[str]:
    try:
        with open(_state_path(session), encoding="utf-8") as fh:
            return set(json.load(fh))
    except Exception:
        return set()


def _remember(session: str, key: str) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        cur = _seen(session)
        cur.add(key)
        with open(_state_path(session), "w", encoding="utf-8") as fh:
            json.dump(sorted(cur), fh)
    except Exception:
        pass


def worst_repeat(transcript_path: str):
    """(signature, count, total_bytes) for the heaviest over-floor repeated string, or None."""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return None

    counts: dict[str, int] = {}
    bytes_: dict[str, int] = {}
    shown: dict[str, str] = {}
    for e in entries:
        text = _entry_text(e)
        if not text:
            continue
        norm = _norm(text)
        key = hashlib.sha1(norm[:SIG_LEN].encode("utf-8", "replace")).hexdigest()
        counts[key] = counts.get(key, 0) + 1
        bytes_[key] = bytes_.get(key, 0) + len(text)
        if key not in shown:
            shown[key] = norm[:SIG_LEN]

    best = None
    for key, c in counts.items():
        if c >= COUNT_FLOOR and bytes_[key] >= BYTE_FLOOR:
            if best is None or bytes_[key] > best[2]:
                best = (key, shown[key], c, bytes_[key])
    return best


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    hit = worst_repeat(transcript)
    if not hit:
        return 0
    key, sig, count, total = hit
    session = payload.get("session_id") or os.path.basename(transcript)
    if key in _seen(session):
        return 0                      # already flagged this leak once — do not re-nag every turn
    _remember(session, key)

    pct = total / 1_000_000 * 100     # tokens ≈ bytes/4, but bytes vs a 1M-token window is the
    #                                   right order of magnitude and needs no model lookup here.
    looks_like_hook = any(m in sig for m in (
        "was not found", "Traceback", "non-blocking", "Error:", "cannot", "No such file"))
    culprit = ("  This looks like a repeated tool/plugin/hook ERROR. Check the hook + plugin "
               "configs (settings.json, ~/.claude/plugins/*/hooks/hooks.json) — a hook that "
               "fails non-blocking floods every turn with the same stderr.\n" if looks_like_hook
               else "")
    reason = (
        f"Context leak: one string appears {count}x for ~{total:,} bytes "
        f"(~{total // 4:,} tokens, ~{pct:.0f}% of a 1M window) — more than any single message "
        f"should cost. An aggregate context % hides this; the bytes are real.\n"
        f"{culprit}"
        f"  The repeated string starts:\n    {sig[:240]!r}\n"
        f"  Find and stop the source, or (if it is a known, accepted cost) note it. This fires "
        f"ONCE per leak per session; it will not nag again."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Stop check: a stated context figure must be MEASURED, and a wind-down must carry its provenance.

WHY THIS EXISTS
---------------
2026-08-01: a conductor announced "~48% context", then "~50%", then "I'm at ~65%", and wound the
run down on the strength of it. The real figure was 39%. Nothing was measured -- the numbers were
produced by the feeling of a long session, which is exactly the thing an agent cannot sense. The
brief already said "read it from your own transcript, never *feel* it"; that is Voluntary class
and it decayed inside one run, in the direction that ends runs early. Brad's instruction, verbatim:

    "if you want to wind down, you have to state the context and provenance of that value, and
     provenance must be measured not guessed."

and, on the general case: "mechanically forbid it".

WHAT IT CHECKS
--------------
Two objections, deliberately narrow so this cannot become the guard that cries wolf:

  A. DISAGREEMENT -- the turn states a percentage near the word "context"/"window" that differs
     from the transcript's own arithmetic by more than TOLERANCE_PTS. This cannot be satisfied by
     asserting anything, because the hook computes the true value itself and prints it. It is
     strictly better than demanding a tool call: the model cannot lie past it, and it is handed
     the right answer instead of a chore.

  B. WIND-DOWN BELOW THE GUN -- the turn asserts a wind-down while the measured figure is under
     WINDDOWN_GUN_PCT. Escape: `winddown:early <reason>`, which is auditable in the transcript.

     This started life as "state the figure and its provenance", and Brad replaced it the same
     hour with something strictly better: *"instead of saying 'you need to measure that and say
     where you got it' we should make the hook check the context value, itself, and verify it's
     >49%."* That removes the prose chore entirely -- there is nothing to assert, nothing to
     forget, and nothing an agent can satisfy by writing a sentence. The hook already knows the
     number, so it should enforce the precondition rather than ask to be told about it.

     It also closes the failure the wind-down skill's Precondition 0 describes but cannot
     prevent: winding down because the queue *looks* drained. That has been wrong every time,
     and it is now unrepresentable below the gun without an explicit, logged reason.

DESIGN
------
* Uses the SAME arithmetic as ~/.claude/context-usage.py -- input + cache_creation + cache_read
  against the model's window. Two instruments that disagree about the same quantity are worse
  than one, and this project has already paid for that once.
* FAIL-OPEN everywhere. A guard that can hold a turn hostage on its own bug is worse than the
  error it hunts.
* Only inspects THIS turn's assistant text, so an old figure quoted in history cannot re-fire.

WHAT IT CANNOT DO
-----------------
It cannot catch a context claim phrased without a number ("I'm running low on room"), and it
cannot judge whether winding down is the RIGHT call at a correctly-measured figure. It raises the
floor; it does not make the decision.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

TOLERANCE_PTS = 10.0

# The wind-down start gun (Brad, 2026-08-01, lowered from 60%). Below this, a wind-down is
# premature and the hook refuses it OUTRIGHT rather than asking for provenance -- see the
# WHAT IT CHECKS note. Change this when the gun changes; it is the one number here that is policy.
WINDDOWN_GUN_PCT = 50.0

# Auditable escape, same shape as `# guard:ok` and `evidence:none`. A wind-down below the gun is
# legitimate when Brad asks for one, when the work is genuinely finished, or in an emergency --
# so the token requires a REASON after it, and its use is visible in the transcript forever.
_EARLY_OK = re.compile(r"winddown:early\s+\S", re.I)

# A percentage within this many characters of a context word counts as a context claim.
_NEAR = 45
_NEAR_POLICY = 22   # a threshold word attaches to its own number; a wider window swallows the claim beside it

_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_CONTEXT_WORD = re.compile(r"context|window|of\s*1M|of\s*200k", re.I)

# A percentage near "context" is not necessarily a claim about the CURRENT state -- it is just as
# likely to be a THRESHOLD being discussed ("the brief says wind down at 50% context"). Both
# markers are matched against the individual percentage's own window, not the whole message, so
# one sentence can carry a suppressed threshold and a live claim at once:
#   "I'm at 65% context, past the 50% gun"  ->  65 is judged, 50 is not.
# Policy wins over state, because a false BLOCK is what gets a guard switched off, and this hook
# still catches the case that matters most (winding down) through a separate path.
_STATE = re.compile(
    r"i'?m|i am|we'?re|we are|currently|right now|so far|"
    r"context (?:is|sits|stands|used|remaining)|used|remaining|burned|spent|"
    r"context\s*~?\d|of\s*1M|of\s*200k",   # the canonical measured forms
    re.I,
)
_POLICY = re.compile(
    r"wind[-\s]?down(?:ing)? at|gun|ceiling|threshold|limit|budget|policy|rule|says|"
    r"should|must|when (?:i|we) (?:hit|reach)|start(?:ing)? at|stop at|below|above|under|over",
    re.I,
)

# Assertive wind-down only. "should I wind down?" and "wind down at 50%" must not fire.
_WINDDOWN = re.compile(
    r"(wind(?:ing)?[-\s]?down\s+(?:is\s+)?(?:complete|done|finished)"
    r"|(?:i(?:'m| am)\s+)?(?:now\s+)?wind(?:ing)?\s+down\b"
    r"|starting\s+(?:the\s+)?wind[-\s]?down"
    r"|handoff\s+is\s+(?:written|committed))",
    re.I,
)

_MEASURED = re.compile(r"pct_of_1M|pct_of_200k|context-usage\.py|context\s+\d{1,3}%", re.I)

_WINDOWS = {
    "opus-5": 1_000_000, "fable-5": 1_000_000, "mythos-5": 1_000_000,
    "opus-4-8": 1_000_000, "opus-4-7": 1_000_000, "opus-4-6": 1_000_000,
    "sonnet-5": 1_000_000, "sonnet-4-6": 1_000_000,
}


def window_for(model: str) -> int:
    m = (model or "").lower()
    for key, win in _WINDOWS.items():
        if key in m:
            return win
    return 200_000


def _entries(path: str):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _this_turn(rows):
    """Assistant text and tool-result text since the last user entry."""
    last_user = 0
    for i, r in enumerate(rows):
        if r.get("type") == "user" or (r.get("message") or {}).get("role") == "user":
            last_user = i
    said, saw = [], []
    for r in rows[last_user:]:
        msg = r.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            (said if msg.get("role") == "assistant" else saw).append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    (said if msg.get("role") == "assistant" else saw).append(block.get("text") or "")
                elif block.get("type") == "tool_result":
                    c = block.get("content")
                    if isinstance(c, str):
                        saw.append(c)
                    elif isinstance(c, list):
                        for b in c:
                            if isinstance(b, dict) and b.get("type") == "text":
                                saw.append(b.get("text") or "")
    return "\n".join(said), "\n".join(saw)


def _true_pct(rows) -> tuple[float | None, int, int]:
    for r in reversed(rows):
        msg = r.get("message") or {}
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        total = ((usage.get("input_tokens") or 0)
                 + (usage.get("cache_creation_input_tokens") or 0)
                 + (usage.get("cache_read_input_tokens") or 0))
        if total <= 0:
            continue
        win = window_for(msg.get("model") or "")
        return 100.0 * total / win, total, win
    return None, 0, 0


def _context_claims(text: str) -> list[float]:
    out = []
    for m in _PCT.finditer(text):
        lo = max(0, m.start() - _NEAR)
        hi = min(len(text), m.end() + _NEAR)
        near = text[lo:hi]
        if not _CONTEXT_WORD.search(near):
            continue
        # A percentage inside a code span is being QUOTED, not asserted -- a test fixture, a
        # sample block message, a doc snippet. Measured 2026-08-01 on this guard's own first
        # live turn: it fired on `"I'm at 65% context, past the 50% gun"` quoted from its own
        # test suite. Backtick parity before the match is a cheap, reliable test for that.
        if text.count("`", 0, m.start()) % 2 == 1:
            continue
        tight = text[max(0, m.start() - _NEAR_POLICY):min(len(text), m.end() + _NEAR_POLICY)]
        if _POLICY.search(tight):         # a threshold, not a reading
            continue
        if not _STATE.search(near):       # nothing says this is the CURRENT value
            continue
        try:
            out.append(float(m.group(1)))
        except Exception:
            pass
    return out


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return 0
    try:
        rows = list(_entries(path))
        said, saw = _this_turn(rows)
        truth, total, win = _true_pct(rows)
    except Exception:
        return 0
    if truth is None or not said:
        return 0

    human_win = "1M" if win >= 1_000_000 else f"{win // 1000}k"
    real = (f"MEASURED NOW, from this transcript: **{truth:.0f}% of {human_win}** "
            f"({total:,} tokens = input + cache_creation + cache_read).")
    measured_here = bool(_MEASURED.search(saw) or _MEASURED.search(said))

    claims = _context_claims(said)
    wrong = [c for c in claims if abs(c - truth) > TOLERANCE_PTS]
    if wrong:
        stated = ", ".join(f"{c:g}%" for c in wrong)
        return _block(
            f"YOU STATED A CONTEXT FIGURE THAT IS NOT TRUE: {stated}.\n\n{real}\n\n"
            "You cannot sense context. A figure that was not read from an instrument is a guess "
            "wearing a number, and guesses run in the direction that ends runs early -- on "
            "2026-08-01 a conductor climbed 48% -> 50% -> 65% against a true 39% and wound down "
            "on it.\n\n"
            "Correct the number in a one-line addendum (do NOT rewrite your message). If you want "
            "it yourself rather than from this hook:\n"
            "    python ~/.claude/context-usage.py\n"
            "Read the WHOLE output -- it prints both pct_of_1M and pct_of_200k."
        )

    wd = _WINDDOWN.search(said)
    if wd:
        around = said[max(0, wd.start() - 35):min(len(said), wd.end() + 35)]
        if _POLICY.search(around):
            wd = None                     # "the rule is to wind down at 50%" is not a wind-down
    if wd and truth < WINDDOWN_GUN_PCT and not _EARLY_OK.search(said):
        return _block(
            f"WIND-DOWN REFUSED -- YOU ARE NOT NEAR THE GUN.\n\n{real}\n\n"
            f"The start gun is {WINDDOWN_GUN_PCT:.0f}%. You are at {truth:.0f}%, with "
            f"{WINDDOWN_GUN_PCT - truth:.0f} points of headroom before wind-down is even due -- "
            "so this is not a context decision, and the wind-down skill's Precondition 0 is "
            "explicit that 'everything is blocked on Brad' and 'the queue looks drained' are NOT "
            "triggers. They have been wrong every time.\n\n"
            "Before ending: name three things you considered and chose NOT to do. If you cannot "
            "list three, you have not looked. Go find real work.\n\n"
            "If the wind-down is genuinely warranted anyway -- Brad asked for one, the work is "
            "actually finished, or something is wrong -- say so explicitly with a reason:\n"
            "    winddown:early <your reason>\n"
            "That is logged and stays in the transcript."
        )
    return 0


def _block(reason: str) -> int:
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Self-test for context_claim_guard.py.

Includes the POSITIVE CONTROL that matters: a run where the guard MUST stay silent. A guard that
fires on everything is indistinguishable from a guard that works, right up until someone disables
it -- and this codebase's own doctrine is that such a guard takes its true positives with it.
"""
from __future__ import annotations

import io
import json
import os
import runpy
import sys
import tempfile

# Telemetry isolation -- keep this suite OUT of the live ~/.claude/hook-events.jsonl, the
# one file that says whether a hook works. Must be set before any hook runs; subprocesses
# inherit it. Any new hook test needs these two lines. See hook_log.log_path().
os.environ["HOOK_LOG_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hooklog-test-"), "events.jsonl")


HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "context_claim_guard.py")


def transcript(assistant_text: str, tool_text: str = "", total: int = 390_000,
               model: str = "claude-opus-5") -> str:
    """A minimal 2-entry transcript: one user turn, one assistant turn with usage."""
    rows = [
        {"type": "user", "message": {"role": "user", "content": "go"}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": [{"type": "text", "text": tool_text}]}]}},
        {"type": "assistant", "message": {
            "role": "assistant", "model": model,
            "content": [{"type": "text", "text": assistant_text}],
            "usage": {"input_tokens": 1000, "cache_creation_input_tokens": 9_000,
                      "cache_read_input_tokens": total - 10_000}}},
    ]
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with io.open(fd, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def run(path: str) -> dict:
    payload = json.dumps({"transcript_path": path})
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(payload), io.StringIO()
    try:
        runpy.run_path(GUARD, run_name="__main__")
    except SystemExit:
        pass
    finally:
        out = sys.stdout.getvalue()
        sys.stdin, sys.stdout = old_in, old_out
    return json.loads(out) if out.strip() else {}


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# total 390k of 1M -> truth is 39%.

@case("A: the real 2026-08-01 failure -- claims 65%, truth 39% -> BLOCK")
def _a():
    r = run(transcript("I'm at ~65% context, so I'll start winding down."))
    assert r.get("decision") == "block", r
    assert "39%" in r["reason"], r["reason"]


@case("A2: a claim inside tolerance -> SILENT")
def _a2():
    r = run(transcript("I'm at about 44% context, plenty of room."))
    assert r == {}, r


@case("B: wind-down at 39% -- below the 50% gun -> BLOCK")
def _b():
    r = run(transcript("Wind-down complete. Handoff is written and pushed."))
    assert r.get("decision") == "block", r
    assert "NOT NEAR THE GUN" in r["reason"], r["reason"]
    assert "39%" in r["reason"] and "11 points" in r["reason"], r["reason"]


@case("B2: wind-down at 39% WITH the audited escape -> SILENT")
def _b2():
    r = run(transcript("Wind-down complete. winddown:early the operator asked me to stop here."))
    assert r == {}, r


@case("B3: wind-down ABOVE the gun -> SILENT, and no provenance chore")
def _b3():
    r = run(transcript("Wind-down complete. Handoff is written.", total=720_000))
    assert r == {}, r


@case("B4: a correctly-stated figure above the gun still passes the disagreement check")
def _b4():
    r = run(transcript("I am at 72% context, so I am winding down now.", total=720_000))
    assert r == {}, r


@case("C: POSITIVE CONTROL -- an ordinary turn full of percentages -> SILENT")
def _c():
    r = run(transcript(
        "Coverage rose from 61% to 88%, and 103 of the last 200 events were suppressed. "
        "The rollout sits at 100% for group default. Battery reads 72%."))
    assert r == {}, r


@case("C2: POSITIVE CONTROL -- discussing the rule, not asserting a state -> SILENT")
def _c2():
    r = run(transcript("The brief says to wind down at 50% context; I'm nowhere near that."))
    # 50% vs truth 39% is inside tolerance, and this is not an assertive wind-down.
    assert r == {}, r


@case("D: no usage in the transcript -> FAIL OPEN")
def _d():
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with io.open(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {
            "role": "assistant", "content": [{"type": "text", "text": "I'm at 99% context."}]}}) + "\n")
    assert run(path) == {}, "must fail open when it cannot measure"


@case("E: missing transcript -> FAIL OPEN")
def _e():
    assert run(os.path.join(tempfile.gettempdir(), "definitely-not-here.jsonl")) == {}



@case("C3: a live claim beside a threshold -- judge the claim, not the threshold -> BLOCK")
def _c3():
    r = run(transcript("I'm at 65% context, past the 50% gun, so I'll stop."))
    assert r.get("decision") == "block", r
    assert "65%" in r["reason"] and "50%" not in r["reason"].split("NOT TRUE:")[1][:20], r["reason"]


@case("C4: POSITIVE CONTROL -- pure policy talk -> SILENT")
def _c4():
    r = run(transcript("Wind down at 50% context is the rule; the ceiling is 85% of the window."))
    assert r == {}, r



@case("F: POSITIVE CONTROL -- a percentage QUOTED in a code span -> SILENT")
def _f():
    r = run(transcript('The controls are `\"I am at 65% context, past the 50% gun\"` and one more.'))
    assert r == {}, r


@case("F2: an unquoted claim in the same message still BLOCKS")
def _f2():
    r = run(transcript('The fixture is `65% context` but I am at 78% context right now.'))
    assert r.get("decision") == "block", r
    assert "78%" in r["reason"], r["reason"]


def main() -> int:
    bad = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {name}\n       {exc}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

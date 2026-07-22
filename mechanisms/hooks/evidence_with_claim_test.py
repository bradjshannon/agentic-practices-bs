#!/usr/bin/env python3
"""Tests for evidence_with_claim.

Deliberately weighted toward BENIGN cases. A guard that cries wolf gets disabled and takes its
true positives with it -- so the benign half of this file is the load-bearing half.

Run:  py -3 ~/.claude/hooks/evidence_with_claim_test.py
"""
import os
import runpy
import sys

H = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "evidence_with_claim.py"))
evaluate = H["evaluate"]
find_claims = H["find_claims"]
code_spans = H["code_spans"]

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


# --- SHOULD BLOCK: the three real burns, reconstructed --------------------------------------

check(
    "kill-the-subagent (inferred from proxies, no quote)",
    evaluate("The tree is clean and its output has been stale 7 min, so my concurrent-tree "
             "collision ate that agent's work -- there are no commits carrying it.",
             "git status --short\n(no output)", calls=2)[0],
    True,
)

check(
    "ICAO false alarm (asserted from one directory)",
    evaluate("No -- there isn't one on this machine. Nothing references an ICAO skill.",
             "ls ~/.claude/skills/\nconductor-winddown\ntailnet-comms", calls=1)[0],
    True,
)

check(
    "verification claim with no quoted evidence",
    evaluate("Both connected, telemetry current. Verified twice -- the beeping should be done.",
             "curl localhost:8000/health\n{\"status\":\"ok\"}", calls=3)[0],
    True,
)

check(
    "quote is present but did NOT come from this turn's tool output",
    evaluate("Confirmed: the route is `POST /admin/devices/{id}/plausible` in the app.",
             "curl -s localhost:8000/openapi.json\n{\"paths\": {\"/admin/devices\": {}}}", calls=1)[0],
    True,
)

check(
    "span shorter than MIN_SPAN does not count as evidence",
    evaluate("Confirmed, the health endpoint answers: `ok`.",
             "the literal word ok appears here plus lots of other text", calls=1)[0],
    True,
)


# --- SHOULD NOT BLOCK: benign cases -------------------------------------------------------

check(
    "claim WITH a verbatim quote from this turn",
    evaluate("Confirmed the fix landed: `mic_level=0.0065` in the health snapshot.",
             'GET /admin/devices -> {"health": {"mic_level=0.0065", "uptime_s": 68}}', calls=1)[0],
    False,
)

check(
    "fenced block quoted verbatim counts too",
    evaluate("Verified -- the suite is green:\n```\n2335 passed in 54.9s\n```",
             "PYTHONPATH=src python -m pytest tests/ -q\n2335 passed in 54.9s", calls=1)[0],
    False,
)

check(
    "no tool calls this turn -- pure conversation, nothing to quote",
    evaluate("There is no scenario where I'd push to main unasked.", "", calls=0)[0],
    False,
)

check(
    "no load-bearing claim at all",
    evaluate("Flashed NIMBE and started the build; I'll check telemetry next.",
             "idf.py build\n...", calls=4)[0],
    False,
)

check(
    "HEDGED verification is the honest shape, not an assertion",
    evaluate("The beep fix is not verified on hardware yet -- the outage test hasn't run.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "'unverified' must not trip the verification pattern",
    evaluate("DURIN's AFE path is unverified; COM7 was never connected this run.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "quoting the HUMAN's words in a blockquote is not the agent asserting",
    evaluate("> there is no ICAO skill, right?\n\nI'll go look rather than answer from memory.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "quoting a doc that contains 'confirmed' is not the agent asserting",
    evaluate("From the handoff:\n> **A misfiring guard trains bypass** (CONFIRMED -- a subagent"
             " stayed blocked).\n\nStarting there.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "POST-negation: 'proves nothing' asserts ABSENCE of evidence (first real-world FP)",
    evaluate("Its control ran in the same window, which proves nothing about a collision.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "post-negation: 'confirmed nothing'",
    evaluate("The sweep confirmed nothing new; the finding stands unverified.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "but a bare 'proves' with no negation still needs evidence",
    evaluate("The backtrace proves the stack overflow is in the diag task.",
             "some tool output", calls=1)[0],
    True,
)

check(
    "'should be verified' reads as a plan, not a claim",
    evaluate("That path should be verified on real hardware before we call it done.",
             "some tool output", calls=1)[0],
    False,
)


# --- unit-level ----------------------------------------------------------------------------

check("find_claims picks up both classes",
      sorted({c for c, _ in find_claims("Verified. Also there is no caller outside the test.")}),
      ["negative-existence", "verification"])

check("code_spans respects MIN_SPAN",
      code_spans("short `ok` and long `2335 passed in 54.9s`"),
      ["2335 passed in 54.9s"])

check("blockquote stripping",
      find_claims("> verified by them\nnothing here"), [])


if FAILURES:
    print(f"FAIL ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("evidence_with_claim: all checks passed")

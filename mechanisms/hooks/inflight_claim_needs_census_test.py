#!/usr/bin/env python3
"""Tests for inflight_claim_needs_census.

Deliberately weighted toward BENIGN cases. A guard that cries wolf gets disabled and takes its
true positives with it -- so the benign half of this file is the load-bearing half.

Run:  py -3 ~/.claude/hooks/inflight_claim_needs_census_test.py
"""
import os
import runpy
import sys

H = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "inflight_claim_needs_census.py"))
evaluate = H["evaluate"]
find_claims = H["find_claims"]
claimed_count = H["claimed_count"]

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


# The real batch result shapes, verbatim enough to be representative.
LAUNCH_OK = ("Async agent launched successfully. (This tool result is internal metadata.)\n"
             "agentId: abcd230a9a96fe564")
LAUNCH_ERR = ("You already have a 'general-purpose' agent this session. Reuse it like an SME "
              "rather than paying to prime a new one.")


# --- SHOULD BLOCK: the 2026-08-11 burn, reconstructed ---------------------------------------

check(
    "THE BURN: 1 launch + 5 errors, reported as 3 still running",
    evaluate("3 background subagents still running (dispatched earlier, no completion "
             "notification yet). I'll continue once they land.",
             LAUNCH_OK + "\n" + "\n".join([LAUNCH_ERR] * 5), calls=6)[0],
    True,
)

check(
    "in-flight claim with NO launches and NO census at all",
    evaluate("Those three investigations are still running; I'll act on them when they report.",
             "git status --short\n(no output)", calls=2)[0],
    True,
)

check(
    "every dispatch errored, but the turn claims work is in flight",
    evaluate("The agents are still working in the background.",
             "\n".join([LAUNCH_ERR] * 3), calls=3)[0],
    True,
)

check(
    "claimed count exceeds actual launches",
    evaluate("Four agents are still running on the remaining cards.",
             LAUNCH_OK + "\n" + LAUNCH_ERR, calls=5)[0],
    True,
)

check(
    "'waiting on the background agents' with nothing launched",
    evaluate("Pausing here -- waiting on those background agents before I continue.",
             "some unrelated tool output", calls=1)[0],
    True,
)


# --- SHOULD NOT BLOCK: benign cases ---------------------------------------------------------

check(
    "a real census (TaskList) backs the claim",
    evaluate("Two agents are still running per the task list.",
             "id  subject  status  owner\n1  det-out  in_progress  ab9d\n"
             "2  s4-parity  in_progress  ab74", calls=1)[0],
    False,
)

check(
    "census returned nothing and the agent says so honestly",
    evaluate("Checked the task list -- no agents are running; those never started.",
             "No tasks found", calls=1)[0],
    False,
)

check(
    "claim matches the number actually launched this turn",
    evaluate("Both agents are still running; I'll report when they land.",
             LAUNCH_OK + "\n" + LAUNCH_OK, calls=2)[0],
    False,
)

check(
    "FUTURE tense: dispatching next is a plan, not a state claim",
    evaluate("I'll dispatch three agents next and wait for them to report.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "'let me launch' is intent, not an assertion of liveness",
    evaluate("Let me launch the remaining investigation; it'll be running in the background.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "HONEST correction is the shape this hook wants to produce",
    evaluate("Correcting myself: those three never started -- the dispatch errored, so nothing "
             "is running.",
             "\n".join([LAUNCH_ERR] * 3), calls=3)[0],
    False,
)

check(
    "explicit 'did not launch' is not punished",
    evaluate("Four of the six did not launch, so only one agent is still running.",
             LAUNCH_OK, calls=6)[0],
    False,
)

check(
    "no tool calls -- pure conversation",
    evaluate("They're still running, I think.", "", calls=0)[0],
    False,
)

check(
    "no in-flight claim at all",
    evaluate("Shipped the fix and verified it on S2; moving to the next card.",
             "some tool output", calls=3)[0],
    False,
)

check(
    "past-tense completion is not an in-flight claim",
    evaluate("The agent came back and its findings are already actioned.",
             "some tool output", calls=2)[0],
    False,
)

check(
    "human's words in a blockquote are not the agent asserting",
    evaluate("> are they still running?\n\nLet me check the task list rather than guess.",
             "some tool output", calls=1)[0],
    False,
)

check(
    "a task-notification in the turn counts as a census signal",
    evaluate("One agent is still running; the other just reported.",
             "<task-notification><task-id>abc</task-id><status>completed</status>"
             "</task-notification>", calls=1)[0],
    False,
)


# --- unit-level -----------------------------------------------------------------------------

check("find_claims catches the burn phrasing",
      len(find_claims("3 background subagents still running")) >= 1, True)

check("claimed_count reads a digit near the claim",
      claimed_count("3 background subagents still running"), 3)

check("claimed_count reads a number word",
      claimed_count("three agents are still running"), 3)

check("claimed_count is 0 when no count is stated",
      claimed_count("the agents are still running"), 0)

check("blockquote stripping",
      find_claims("> still running?\nnothing here"), [])

check("honest shape yields no claim",
      find_claims("those never started, nothing is running"), [])


if FAILURES:
    print(f"FAIL ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("inflight_claim_needs_census: all checks passed")

#!/usr/bin/env python3
"""Tests for hedge_demotion_guard.

Weighted toward BENIGN cases on purpose. A guard that cries wolf gets disabled and takes its
true positives with it -- so the benign half is the load-bearing half.

Run:  py -3 ~/.claude/hooks/hedge_demotion_guard_test.py
"""
import os
import runpy
import sys

H = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "hedge_demotion_guard.py"))
evaluate = H["evaluate"]

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


FILLER = ("The catalog is delivered over MCP and the server passes it through to the model. "
          "Each entry carries a name, a description and an input schema. " * 12)


def msg(lead: str, body: str, tail: str) -> str:
    return f"{lead}\n\n{body}\n\n{tail}"


# --- SHOULD BLOCK: the 2026-08-11 fan-tools shape, reconstructed ----------------------------

check(
    "THE BURN: bold lead, caveat only at the very bottom",
    evaluate(msg("**Yes -- fundamentally different, and the fan's are prose.**",
                 FILLER,
                 "Scope caveat: that capture is one agent on one date. "
                 "I haven't verified that this run."), calls=3)[0],
    True,
)

check(
    "'unverified' buried under a bold opener",
    evaluate(msg("**The fan catalog carries no bounds at all.**",
                 FILLER,
                 "This is unverified against the live server."), calls=2)[0],
    True,
)

check(
    "'worth re-checking' demoted to the tail",
    evaluate(msg("**S3 is running the same build as S2.**",
                 FILLER,
                 "Worth re-checking before building on it."), calls=1)[0],
    True,
)


# --- SHOULD NOT BLOCK: benign shapes -------------------------------------------------------

check(
    "caveat placed IN the lead -- the shape this hook wants to produce",
    evaluate(msg("**One 07-28 capture says the fan's are prose -- not checked live.**",
                 FILLER,
                 "I'll verify against S2 next."), calls=3)[0],
    False,
)

check(
    "caveat in the lead AND repeated at the end is good practice, not a defect",
    evaluate(msg("**Unverified: one capture suggests the fan's tools are prose.**",
                 FILLER,
                 "Again, this is unverified."), calls=3)[0],
    False,
)

check(
    "no caveat anywhere -- a different hook's business, not this one's",
    evaluate(msg("**The suite is green at 1327 passed.**",
                 FILLER,
                 "Pushed to test."), calls=2)[0],
    False,
)

check(
    "no bold opener -- prose without a headline creates no skim-and-stop effect",
    evaluate(msg("The fan's tools appear to be prose-defined.",
                 FILLER,
                 "I haven't verified that this run."), calls=2)[0],
    False,
)

check(
    "short message -- no 'bottom' to bury anything in",
    evaluate("**The fan's are prose.** I haven't verified that this run.", calls=1)[0],
    False,
)

check(
    "no tool calls -- pure conversation",
    evaluate(msg("**The fan's are prose.**", FILLER, "I haven't verified this."), calls=0)[0],
    False,
)

check(
    "caveat in the MIDDLE still reaches a reader who skims the opening claim",
    evaluate(msg("**The fan's are prose.**",
                 FILLER + "\n\nI haven't verified that this run.\n\n" + FILLER,
                 "Next I'll check S2."), calls=2)[0],
    False,
)

check(
    "quoting the human's caveat in a blockquote is not the agent hedging",
    evaluate(msg("**The fan's are prose.**",
                 FILLER,
                 "> you haven't verified that\n\nCorrect, checking now."), calls=2)[0],
    # the ONLY hedge was inside a blockquote, so after stripping there is no hedge at all
    False,
)


# --- BOLD-AS-HEADER MUST NOT COUNT AS A CLAIM ----------------------------------------------
# Measured on 1,351 real assistant messages: without this filter the hook fired 10 times and 5
# were section headers or filenames -- a 50% false-positive rate INSIDE its own fires, which is
# how a guard earns a bypass. Each case below is a real bold span taken from those transcripts.

check(
    "bold section header ending in ':' is not a claim",
    evaluate(msg("**Router state for `A4:CB:8F:C2:73:74` (on S1):**",
                 FILLER,
                 "I haven't verified that this run."), calls=2)[0],
    False,
)

check(
    "bold bare filename is not a claim",
    evaluate(msg("**`hook_log.py`**", FILLER, "This is unverified."), calls=2)[0],
    False,
)

check(
    "bold short label is not a claim",
    evaluate(msg("**Status page root cause**", FILLER,
                 "I haven't verified that this run."), calls=2)[0],
    False,
)

check(
    "...but a bold SENTENCE with a buried caveat still fires",
    evaluate(msg("**Zero `ai_device` rows were recreated and no DB writes were made.**",
                 FILLER,
                 "I haven't verified that this run."), calls=2)[0],
    True,
)


# --- unit-level ----------------------------------------------------------------------------

_, facts = evaluate(msg("**Yes -- fundamentally different, and the fan's are prose.**",
                        FILLER, "I haven't verified that this run."), calls=3)
check("facts name the bold lead", facts["bold_in_lead"].startswith("Yes -- fundamentally"), True)
check("facts count the hedges", facts["hedges"] >= 1, True)
check("facts locate the first hedge late in the message", facts["first_hedge_at"] > 0.65, True)


if FAILURES:
    print(f"FAIL ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("hedge_demotion_guard: all checks passed")

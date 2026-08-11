#!/usr/bin/env python3
"""Stop hook: a caveat may not be DEMOTED below the confident claim it qualifies.

WHY THIS HOOK EXISTS
--------------------
2026-08-11, server-conductor run. Asked whether the fan's tool definitions were prose, the
agent answered with a bold lead --

    **Yes -- fundamentally different, and the fan's are prose.**

-- and put the qualifier at the very bottom of the same message:

    Scope caveat: that capture is one agent on one date ... I haven't verified that this run.

The claim rested on ONE repo document and no live check. It was wrong: the next message, after
one SSH session, inverted it. Brad's response was the sharpest question of the session --
*"Why should I believe you, when you confidently correct things you confidently just said?"*

THE DEFECT IS NOT THE ERROR. It is that **the uncertainty was present and demoted.** The agent
had already written the disqualifying sentence; it just placed it where a reader who stops at
the headline never reaches it. Nothing in the message was a lie, and the message was still
misleading, because confidence was allocated by FORMATTING rather than by evidence.

This is a different class from the two hooks next to it, and neither can see it:
  * `evidence_with_claim` asks whether ANY evidence exists. Here it did -- a real document.
  * `inflight_claim_needs_census` asks whether a dispatch actually happened. Unrelated.
Both police the presence of evidence. This one polices the PLACEMENT of the hedge, which is
the only part a skimming reader's belief actually depends on.

THE COUPLING
------------
Position is not a matter of opinion, so it is cheap to check and hard to satisfy accidentally:
if every hedge in a message sits in the closing third while a bold assertion opens it, the
caveat has been demoted. The fix is free and mechanical -- move the qualifier into the lead --
and there is no way to satisfy the check except by actually moving it, because the hook
compares offsets, not wording. An agent cannot talk its way past an offset.

SCOPE GUARDS (each is a false positive that would discredit the hook)
  * Only fires when a hedge EXISTS. A message with no caveat at all is not this failure -- it
    is `evidence_with_claim`'s business, not this hook's.
  * Only fires when the message opens with a BOLD assertion. Prose without an emphatic
    headline does not create the skim-and-stop effect this exists to prevent.
  * Short messages are skipped: in a few hundred characters there is no "bottom" to bury
    anything in, and the whole text is the lead.
  * A hedge anywhere in the opening zone clears the check outright, however many also appear
    later. Repeating a caveat at the end is good practice, not a defect.

OVERRIDE
--------
`hedge:placed` proceeds, logged as `overridden` / `preemptive` exactly like its two siblings, so
detaching it into a standing header shows up as decay rather than passing silently.
"""
import json
import os
import re
import sys

OVERRIDE = re.compile(r"hedge:\s*placed\b", re.I)

# Below this, there is no "bottom of the message" to bury a caveat in.
MIN_CHARS = 900

# Fractions of the message treated as the opening and the closing zones.
LEAD_FRAC = 0.35
TAIL_FRAC = 0.35

# A bold span has to carry some content to count as a headline assertion.
_BOLD = re.compile(r"\*\*([^*\n]{12,})\*\*")

# Bold is used for two different jobs and only one of them creates the skim-and-stop effect:
# an ASSERTION ("**the fan's are prose.**") vs a LABEL or section header ("**Three lines:**",
# "**`hook_log.py`**", "**Status page root cause**"). Measured on 1,351 real assistant messages
# across 12 transcripts: without this filter the hook fires 10 times, and 5 of those are headers
# -- a 50% false-positive rate inside its own fires, which is how a guard earns a bypass. With
# it, the header hits drop out and the genuine claims (including the fan-tools burn this hook
# was written for) still fire.
_MIN_LEAD_WORDS = 5


def _is_assertion(text: str) -> bool:
    """True when a bold span reads as a CLAIM rather than a label or section header."""
    t = text.strip()
    if t.endswith(":"):
        return False                       # "**Three lines:**" -- a header
    if len(t.split()) < _MIN_LEAD_WORDS:
        return False                       # "**Status page root cause**" -- a label
    stripped = t.strip("`")
    if re.fullmatch(r"[\w./\\-]+", stripped):
        return False                       # "**`hook_log.py`**" -- a bare identifier
    return True

# Qualifiers that CONCEDE something about the strength of a claim. Deliberately narrow: these
# are the words used when an agent knows its evidence is thin. Generic uncertainty ("might",
# "probably") is excluded -- it is ordinary prose and gating it would fire constantly.
_HEDGE = re.compile(
    r"(?:"
    r"haven'?t (?:verified|confirmed|checked)|have not (?:verified|confirmed|checked)|"
    r"not (?:independently )?(?:verified|confirmed)|unverified|"
    r"did ?n'?t (?:verify|confirm|check)|"
    r"worth (?:re-?checking|checking|confirming)|"
    r"scope caveat|one caveat|caveat:|"
    r"single[- ]sourced?|one (?:capture|document|source|run|sample)|"
    r"from memory|i infer\b|inference only|"
    r"no live check|not checked live|before building on"
    r")",
    re.I,
)


def strip_blockquotes(text: str) -> str:
    """Quoted lines are the human or a doc speaking, not the agent asserting."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))


def evaluate(said: str, calls: int) -> tuple[bool, dict]:
    """(would_block, facts). Pure, so tests drive it without a transcript."""
    facts = {"chars": 0, "bold_in_lead": None, "hedges": 0, "first_hedge_at": None}
    if calls < 1:
        return False, facts

    body = strip_blockquotes(said)
    n = len(body)
    facts["chars"] = n
    if n < MIN_CHARS:
        return False, facts

    lead_end = int(n * LEAD_FRAC)
    tail_start = int(n * (1.0 - TAIL_FRAC))

    bold_lead = None
    for m in _BOLD.finditer(body):
        if m.start() <= lead_end and _is_assertion(m.group(1)):
            bold_lead = m.group(1).strip()
            break
    facts["bold_in_lead"] = bold_lead
    if not bold_lead:
        return False, facts

    hedges = [m.start() for m in _HEDGE.finditer(body)]
    facts["hedges"] = len(hedges)
    if not hedges:
        # No caveat at all is a different failure -- evidence_with_claim's, not this one's.
        return False, facts
    facts["first_hedge_at"] = round(hedges[0] / n, 2)

    # A hedge anywhere in the opening zone clears it, however many follow later.
    if any(h <= lead_end for h in hedges):
        return False, facts

    # Demotion: every caveat sits in the closing zone, under a bold opener.
    if all(h >= tail_start for h in hedges):
        return True, facts
    return False, facts


def turn(transcript_path: str) -> tuple[str, int]:
    """(assistant text this turn, tool-call count). Mirrors evidence_with_claim.turn."""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return "", 0

    start = 0
    for i in range(len(entries) - 1, -1, -1):
        content = (entries[i].get("message") or {}).get("content")
        if entries[i].get("type") == "user" and isinstance(content, str) and content.strip():
            start = i
            break

    said, calls = [], 0
    for e in entries[start:]:
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        is_assistant = e.get("type") == "assistant"
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and is_assistant:
                said.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                calls += 1
    return "\n".join(said), calls


def _log(event: str, trigger: str, transcript: str, extra: dict) -> None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("hedge_demotion_guard", trigger=trigger,
                        transcript_path=transcript, extra=dict(extra, event=event))
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    said, calls = turn(transcript)
    would_block, facts = evaluate(said, calls)
    overridden = bool(OVERRIDE.search(said))

    if overridden:
        _log("overridden" if would_block else "preemptive",
             (facts.get("bold_in_lead") or "")[:80], transcript, facts)
        return 0

    if not would_block:
        return 0

    pct = int((facts["first_hedge_at"] or 0) * 100)
    reason = (
        "This message opens with a bold claim and puts every caveat in the closing third.\n\n"
        f"  bold lead:        **{facts['bold_in_lead'][:110]}**\n"
        f"  caveats:          {facts['hedges']}, first one at {pct}% through the message\n\n"
        "On 2026-08-11 the fan-tools answer led with **\"Yes -- fundamentally different, and "
        "the fan's are prose\"** and closed with \"I haven't verified that this run\". The claim "
        "rested on one document and no live check, and one SSH session inverted it. Brad: "
        "\"Why should I believe you, when you confidently correct things you confidently just "
        "said?\"\n\n"
        "The error is not the defect -- the DEMOTION is. The disqualifying sentence was already "
        "written; it was placed where a reader who stops at the headline never reaches it. "
        "Confidence got allocated by formatting instead of by evidence.\n\n"
        "FIX: move the qualifier INTO the lead, so the first sentence carries the evidence "
        "level.\n"
        "  demoted:  **Yes, the fan's are prose.**  ... (12 paragraphs) ... I haven't checked live.\n"
        "  placed:   **One 07-28 capture says the fan's are prose -- not checked live.**\n\n"
        "If the caveat genuinely qualifies only a side point and not the headline, say so where "
        "the headline is, or override with `hedge:placed` (logged, including pre-emptive use)."
    )
    _log("fire", (facts.get("bold_in_lead") or "")[:80], transcript, facts)
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

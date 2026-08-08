#!/usr/bin/env python3
"""Stop hook: a load-bearing CLAIM must carry evidence that actually exists in this turn.

WHY THIS HOOK EXISTS (and why it is different from the other four)
------------------------------------------------------------------
Three independent cold reads of three sessions converged on one defect, phrased by the agent
itself as: **"asserting X when I only established Y, where Y is a cheap proxy for X."**

The three most expensive instances, all real:

  * "my concurrent-tree collision ate that agent's work" -- inferred from a branch flip, an
    empty `git status`, and a stale output file. It was FALSE; the agent was mid-edit. The
    conclusion was acted on: a live subagent was killed. The refuting check (`ls <the file>`)
    was one command and was run AFTER the kill.
  * "there isn't an ICAO skill on this machine" -- asserted from a search of ONE directory.
    The skill was plugin-provided and listed in the agent's own roster. Cost: ~12h 40m of
    forensics, a false "it's gone" verdict, and a retraction buried in a footnote.
  * "the beeping should be done ... verified twice" -- the verification covered one cue path
    in a healthy state; the symptom was a different cue. The human re-reported it three times.

Every one of those is the same shape, and NONE of the existing guards can see it, because
every existing guard watches a **tool name** (`repo_doc_guard` -> Write/Edit, silent on 62
Bash heredoc writes) or a **string in the output** (`output_budget` -> a token that costs one
line; `requirement_before_mechanism` -> a line starting `Requirement:`). A proxy you can
satisfy without doing the real thing is theatre. The agent itself wrote the test, then did not
apply it:

    "is there a syntactic proxy tightly enough coupled to the semantic behavior that you
     can't satisfy the proxy without doing the real thing?"

THE COUPLING
------------
There is exactly one: **the evidence must be quoted verbatim from a tool result produced in
this same turn, and the hook checks that the quote is really there.** You cannot write that
quote without having actually run the check that produced it. The syntactic artifact (a
backticked span) is not satisfiable by intent, effort, or good faith -- only by having run
something. That is the property none of the other guards have.

WHAT IT DOES
------------
On Stop, for the current turn:
  1. Find load-bearing claims in the assistant's chat text -- deliberately NARROW: negative
     existence ("there is no X", "nothing calls it", "X is gone") and verification
     ("verified", "confirmed", "proven"). Those two classes are the ones that burned; a
     broader net would cry wolf, get disabled, and take its true positives with it.
  2. If any fired, require >=1 code-span in the turn's text that appears VERBATIM in one of
     this turn's tool results.
  3. If none does, block once, naming the claim and what to paste.

SCOPE GUARDS (each one is a false positive that would have discredited the hook)
  * Only fires on turns that made >=1 tool call. A pure-conversation turn has nothing to
    quote, and taxing it would train the escape token as a standing header -- the exact decay
    measured in the other three hooks (27 `# guard:ok` against 8 fires; 26 budget tokens
    against 15 fires).
  * Claim text inside a blockquote (`> ...`) is ignored -- that is the human or a doc being
    quoted, not the agent asserting.
  * Negated/hedged forms ("not verified", "unverified", "isn't proven") are ignored: those are
    the honest shape this hook is trying to produce, not the one it polices.

OVERRIDE, AND WHY ITS USE IS LOGGED
-----------------------------------
`evidence:none` proceeds. But unlike `output_budget` -- which returns SILENTLY when its token
is present, so `grep -c overridden ~/.claude/hook-events.jsonl` returns 0 and its own rollup
is blind -- this hook logs BOTH:
  * `overridden`  -- the token was present on a turn that would have blocked.
  * `preemptive`  -- the token was present on a turn that would NOT have blocked, i.e. it has
    detached from the hook and become part of the standing report format. That is the decay
    signature measured in all three existing hooks, and it was invisible by construction
    because a rollup that iterates FIRES can never see a token emitted before any fire.
Making the decay visible is the point: a hook whose override rate climbs is indictable.
"""
import json
import os
import re
import sys

OVERRIDE = re.compile(r"evidence:\s*none\b", re.I)

# Minimum length for a quoted span to count. Short spans (`ok`, `main`, `0`) appear verbatim in
# almost any tool output by chance, which would make the check satisfiable without evidence.
MIN_SPAN = 12

# --- claim detection -------------------------------------------------------------------
# NARROW ON PURPOSE. Each pattern below corresponds to a claim class that produced a
# confident wrong conclusion in a real run. Do not broaden without a burn to point at.

_NEGATIVE_EXISTENCE = [
    r"there (?:is|are|was|were) no\b",
    r"there (?:isn't|aren't|wasn't|weren't)\b",
    r"do(?:es)? not exist\b",
    r"do(?:es)?n't exist\b",
    r"no such\b",
    r"(?:is|are|it's|its) gone\b",
    r"nothing (?:calls|references|reads|uses|imports|matches|found)\b",
    r"no (?:caller|callers|references?|matches?|traces?|evidence|record)\b",
    r"never (?:ran|fired|happened|called|executed)\b",
    r"zero \w+ (?:found|exist|logged)\b",
]

_VERIFICATION = [
    r"\bverified\b",
    r"\bconfirmed\b",
    r"\bproven\b",
    r"\bproves\b",
]

# Hedged / negated forms -- the HONEST shape. If the claim word is preceded by one of these
# within a few characters, it is a disclaimer, not an assertion.
# The trailing window (was a bare `\s*$`) exists because ADJACENCY was too strict, measured
# 2026-08-08 against 18 days of this hook's own log. `not verified` was excused correctly, but
# `not a verified claim` and `I haven't built or verified that split` were BLOCKED AS ASSERTIONS
# -- i.e. the hook fired hardest on the honest hedged shape it exists to produce, which is the
# cry-wolf failure the _HEDGE_AFTER comment below already names. False positives were 36% of
# override episodes.
#
# The window is deliberately bounded and MUST NOT cross a clause terminator: `[^.!?;:]` is what
# stops "This is not the place. I verified the fix." from having its real claim excused by a
# `not` in the previous sentence. 40 chars covers the observed misses ("a", "built or",
# "yet been") with no room for a whole clause. Widening this further trades a false positive for
# a false negative, and a false negative here is silent -- do not raise it without re-running
# the both-directions controls in evidence_with_claim_test.py.
_HEDGE = re.compile(
    r"(?:\bnot\b|\bun|\bisn't\b|\bwasn't\b|\bnever\b|\bcan't be\b|\bcannot be\b|\byet to be\b|"
    # haven't/hasn't/hadn't/don't/doesn't/didn't were MISSING while isn't/wasn't were present --
    # same class of negation, no reason for the split. "I haven't built or verified that split"
    # was a real blocked-honest-hedge in the 2026-08-08 log sample.
    r"\bhaven't\b|\bhasn't\b|\bhadn't\b|\bdon't\b|\bdoesn't\b|\bdidn't\b|\bcouldn't\b|\bwon't\b|"
    r"\bwithout being\b|\bneeds? to be\b|\bwants? to be\b|\bshould be\b)"
    r"[^.!?;:]{0,40}$",
    re.I,
)

# POST-negation: the negation FOLLOWS the claim word. Caught by this hook's first real fire on
# 2026-07-22 -- "which proves nothing about a cross-run collision" is a statement that evidence
# is ABSENT, i.e. the honest shape, and it was blocked as an assertion because _HEDGE only looks
# backwards. A guard that cries wolf gets routed around and takes its true positives with it, so
# a false positive found in the wild is a defect to fix immediately, not a curiosity.
_HEDGE_AFTER = re.compile(r"^\s*(?:nothing\b|little\b|no\b|not\b|neither\b)", re.I)

_CLAIM_RES = [(re.compile(p, re.I), cls)
              for p, cls in ([(p, "negative-existence") for p in _NEGATIVE_EXISTENCE]
                             + [(p, "verification") for p in _VERIFICATION])]

# Inline `code`, ``code``, and fenced blocks.
_CODE_SPAN = re.compile(r"```[\w+-]*\n(.*?)```|`([^`\n]+)`", re.S)


def strip_blockquotes(text: str) -> str:
    """Drop quoted lines -- those are the human or a doc speaking, not the agent asserting."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))


def find_claims(text: str) -> list[tuple[str, str]]:
    """[(class, the matched sentence fragment)] for load-bearing claims in `text`."""
    body = strip_blockquotes(text)
    out = []
    for rx, cls in _CLAIM_RES:
        for m in rx.finditer(body):
            preceding = body[max(0, m.start() - 24):m.start()]
            if _HEDGE.search(preceding):
                continue
            if _HEDGE_AFTER.match(body[m.end():m.end() + 16]):
                continue
            lo = max(0, m.start() - 60)
            hi = min(len(body), m.end() + 60)
            out.append((cls, " ".join(body[lo:hi].split())))
    return out


def code_spans(text: str) -> list[str]:
    spans = []
    for m in _CODE_SPAN.finditer(text):
        s = (m.group(1) or m.group(2) or "").strip()
        if len(s) >= MIN_SPAN:
            spans.append(s)
    return spans


def _norm(s: str) -> str:
    return " ".join(s.split())


def turn(transcript_path: str) -> tuple[str, str, int]:
    """Delegates to the shared window; see the fallback below for why the local copy remains.

    The local implementation treated a background-task notification as human input, so the
    "quoted verbatim from a tool result in THIS turn" check scoped to a window that began at a
    notification — evidence produced earlier in the real turn looked absent, and the hook could
    demand a quote for a claim whose support was two notifications back. Measured: 25 fake
    boundaries against 37 real ones in a single session.
    """
    # The local copy is deleted deliberately: it was the buggy boundary (a <task-notification>
    # reset the window), and a fallback to it would silently reintroduce exactly the defect the
    # shared module fixes. On import failure, fail OPEN (no claims checked, hook passes) rather
    # than fall back to the wrong answer.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from turn_window import turn as _shared
        t = _shared(transcript_path)
        return t["said"], t["tool_results"], t["tool_calls"]
    except Exception:
        return "", "", 0


def _log(event: str, trigger: str, transcript: str, extra: dict) -> None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("evidence_with_claim", trigger=trigger,
                        transcript_path=transcript, extra=dict(extra, event=event))
    except Exception:
        pass


def evaluate(said: str, results: str, calls: int) -> tuple[bool, list[tuple[str, str]]]:
    """(would_block, claims). Pure, so the tests can drive it without a transcript."""
    if calls < 1:
        return False, []
    claims = find_claims(said)
    if not claims:
        return False, []
    haystack = _norm(results)
    for span in code_spans(said):
        if _norm(span) in haystack:
            return False, claims
    return True, claims


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed payload

    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    said, results, calls = turn(transcript)
    would_block, claims = evaluate(said, results, calls)
    overridden = bool(OVERRIDE.search(said))

    if overridden:
        # Log BOTH shapes. `preemptive` is the decay signature the other hooks cannot see.
        _log("overridden" if would_block else "preemptive",
             claims[0][1] if claims else "(no claim detected)",
             transcript, {"claims": len(claims)})
        return 0

    if not would_block:
        return 0

    shown = "\n".join(f"  [{cls}] ...{frag}..." for cls, frag in claims[:3])
    reason = (
        "This turn asserts a load-bearing claim with no evidence quoted from its own tool "
        "output:\n\n" + shown + "\n\n"
        "Negative-existence and verification claims are the two classes that produced the "
        "costliest wrong conclusions in this project: a live subagent killed on an inferred "
        "stall (the refuting check was one command, run after the kill); a 12h forensic hunt "
        "for a skill that was never missing, asserted from a search of one directory; a "
        "'verified twice' fix the human then re-reported three times.\n\n"
        "FIX: paste the actual evidence -- at least "
        f"{MIN_SPAN} characters, in backticks, copied VERBATIM from a tool result in THIS "
        "turn. The hook checks the quote really appears there, which is the whole point: you "
        "cannot satisfy it without having run the check.\n"
        "  weak:  'confirmed, the route exists'\n"
        "  ok:    'confirmed: `POST /admin/devices/{id}/say` in the live OpenAPI'\n\n"
        "If the claim is genuinely not evidenced -- an inference, a plan, a recollection -- "
        "then either say so in words (\"I infer\", \"not verified\") and the claim patterns "
        "stop matching, or emit `evidence:none`. Override use is LOGGED, including "
        "pre-emptive use, so the decay is visible."
    )
    _log("fire", claims[0][1], transcript, {"claims": len(claims)})
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

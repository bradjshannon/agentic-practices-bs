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
_HEDGE = re.compile(
    r"(?:\bnot\b|\bun|\bisn't\b|\bwasn't\b|\bnever\b|\bcan't be\b|\bcannot be\b|\byet to be\b|"
    r"\bwithout being\b|\bneeds? to be\b|\bwants? to be\b|\bshould be\b)\s*$",
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
    """(assistant text this turn, concatenated tool-result text this turn, tool-call count).

    A user entry with STRING content is real human input and starts the turn; a list-shaped one
    is a tool result being fed back, which stays INSIDE the turn.
    """
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return "", "", 0

    start = 0
    for i in range(len(entries) - 1, -1, -1):
        content = (entries[i].get("message") or {}).get("content")
        if entries[i].get("type") == "user" and isinstance(content, str) and content.strip():
            start = i
            break

    said, results, calls = [], [], 0
    for e in entries[start:]:
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        is_assistant = e.get("type") == "assistant"
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text" and is_assistant:
                said.append(block.get("text") or "")
            elif kind == "tool_use":
                calls += 1
            elif kind == "tool_result":
                c = block.get("content")
                if isinstance(c, str):
                    results.append(c)
                elif isinstance(c, list):
                    for sub in c:
                        if isinstance(sub, dict) and sub.get("type") == "text":
                            results.append(sub.get("text") or "")
    return "\n".join(said), "\n".join(results), calls


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

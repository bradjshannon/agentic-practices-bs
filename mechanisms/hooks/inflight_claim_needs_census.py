#!/usr/bin/env python3
"""Stop hook: claiming background work is IN FLIGHT requires a census that says so.

WHY THIS HOOK EXISTS
--------------------
2026-08-11, server-conductor run. The agent dispatched a batch of six `Agent` calls in one
message. **One launched. Five returned errors** -- the harness caps concurrent agents per
subagent_type, so five came back as:

    You already have a 'general-purpose' agent this session.

The agent read the batch result as a success, and reported to the human:

    "3 background subagents still running (dispatched earlier, no completion notification yet)"

Zero of those three existed. The human had to catch it -- *"confirm they're alive? i see nothing
in background"* -- and every minute between the false report and that question was spent waiting
on work that was never going to arrive.

This is the same family as the burn behind `evidence_with_claim` (asserting X having established
only a proxy for X), but that hook cannot see this one: "3 subagents still running" is neither a
negative-existence claim nor a verification claim, so none of its patterns match. The proxy here
is subtler and worse -- **a dispatch ATTEMPT was read as a dispatch**, and the tool result that
said otherwise was in the agent's own context, unread.

THE COUPLING
------------
The same property that makes `evidence_with_claim` work: you cannot satisfy this hook without
having actually run something. A claim that background work is alive must be backed, IN THE SAME
TURN, by either

  * a census -- a `TaskList` / `TaskOutput` / `TaskGet` tool result, or
  * a successful launch marker (`Async agent launched successfully`) from this turn,

and if the claim names a COUNT, that count may not exceed the number of successful launches
observed. Dispatch errors are counted separately and named back, because the failure mode is
precisely miscounting errors as launches.

SCOPE GUARDS (each is a false positive that would discredit the hook)
  * Only fires on turns that made >=1 tool call.
  * Future/intent phrasing ("I'll dispatch", "about to spawn", "let me launch") is NOT a claim
    that something is currently alive.
  * Past-tense completion ("the agent finished", "came back", "returned") is not an in-flight
    claim.
  * Blockquoted text is the human or a doc speaking, not the agent asserting.
  * Explicitly hedged/corrected forms ("never started", "not actually running", "no agents are
    running") are the honest shape this hook exists to produce.

OVERRIDE
--------
`inflight:unverified` proceeds, and its use is logged both as `overridden` (would have blocked)
and `preemptive` (would not have), so detachment into a standing header is visible rather than
silent -- same rationale as `evidence_with_claim`.
"""
import json
import os
import re
import sys

OVERRIDE = re.compile(r"inflight:\s*unverified\b", re.I)

# --- claim detection -----------------------------------------------------------------------
# A claim that background work is CURRENTLY ALIVE. Narrow on purpose.

_INFLIGHT = [
    r"\bstill running\b",
    r"\bstill (?:in flight|going|working|churning)\b",
    r"\b(?:is|are)\s+(?:still\s+)?in flight\b",
    r"\brunning in the background\b",
    r"\bworking in the background\b",
    r"\bin the background (?:right )?now\b",
    r"\bwaiting (?:on|for) (?:the|those|these|\d+)\s*(?:background\s+)?"
    r"(?:agent|agents|subagent|subagents|task|tasks)\b",
    r"\b(?:agent|agents|subagent|subagents|task|tasks)\s+(?:are|is)\s+"
    r"(?:still\s+)?(?:running|active|alive|pending|in progress)\b",
    r"\bhaven't (?:reported|returned|come back|finished)\b",
    r"\bno completion notification\b",
    r"\byet to (?:report|return|finish|complete)\b",
]

# Phrasings that are intent/future, not a state assertion. Checked BEFORE the claim window so a
# sentence like "I'll dispatch three agents and wait for them" does not read as "three are alive".
_FUTURE = re.compile(
    r"\b(?:i'?ll|i will|going to|about to|let me|next(?: step)?|plan to|intend to|"
    r"then i|after that)\b",
    re.I,
)

# Honest/corrected shapes -- the output this hook wants to produce, never to punish.
_HONEST = re.compile(
    r"\b(?:never (?:started|launched|dispatched|ran)|not actually (?:running|alive)|"
    r"no (?:agents?|subagents?|tasks?) (?:are |were )?(?:running|alive|in flight)|"
    r"nothing (?:is )?(?:running|in flight)|did not (?:launch|start|dispatch)|"
    r"didn'?t (?:launch|start|dispatch)|failed to (?:launch|start|dispatch)|"
    r"errored|were never|was never)\b",
    re.I,
)

_CLAIM_RES = [re.compile(p, re.I) for p in _INFLIGHT]

# --- evidence markers, read from THIS TURN's tool results -----------------------------------

# A background Agent dispatch that actually took.
_LAUNCH_OK = re.compile(r"Async agent launched successfully", re.I)

# The exact shape that burned: a dispatch that did NOT take.
_LAUNCH_ERR = [
    re.compile(r"You already have a ", re.I),
    re.compile(r"\bagent .{0,40}(?:cap|limit) reached\b", re.I),
]

# A census: the agent actually asked what is alive.
_CENSUS = [
    re.compile(r"No tasks found", re.I),
    re.compile(r"\bid\b.{0,40}\bstatus\b.{0,40}\bowner\b", re.I | re.S),   # TaskList table
    re.compile(r"\btask[_-]?id\b", re.I),
    re.compile(r"<task-notification>", re.I),
]

# A count in the claim ("3 background subagents still running", "two agents are still running").
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_COUNT_NEAR = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b[^.\n]{0,60}?"
    r"\b(?:agents?|subagents?|tasks?|investigations?|jobs?)\b",
    re.I,
)


def strip_blockquotes(text: str) -> str:
    """Drop quoted lines -- the human or a doc speaking, not the agent asserting."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))


def find_claims(text: str) -> list[str]:
    """Matched fragments asserting background work is currently alive."""
    body = strip_blockquotes(text)
    out = []
    for rx in _CLAIM_RES:
        for m in rx.finditer(body):
            lo = max(0, m.start() - 90)
            hi = min(len(body), m.end() + 60)
            window = body[lo:hi]
            # Intent/future phrasing in the lead-up -> a plan, not a state assertion.
            if _FUTURE.search(body[max(0, m.start() - 60):m.start()]):
                continue
            if _HONEST.search(window):
                continue
            out.append(" ".join(window.split()))
    return out


def claimed_count(text: str) -> int:
    """Largest agent/task count asserted near an in-flight claim, or 0 if none stated."""
    body = strip_blockquotes(text)
    best = 0
    for frag in find_claims(body):
        for m in _COUNT_NEAR.finditer(frag):
            raw = m.group(1).lower()
            n = _WORD_NUM.get(raw, 0) if not raw.isdigit() else int(raw)
            best = max(best, n)
    return best


def count_matches(patterns, results: str) -> int:
    return sum(len(rx.findall(results)) for rx in patterns)


def evaluate(said: str, results: str, calls: int) -> tuple[bool, list[str], dict]:
    """(would_block, claims, facts). Pure, so tests drive it without a transcript."""
    facts = {"launched": 0, "dispatch_errors": 0, "census": False, "claimed": 0}
    if calls < 1:
        return False, [], facts

    claims = find_claims(said)
    if not claims:
        return False, [], facts

    facts["launched"] = len(_LAUNCH_OK.findall(results))
    facts["dispatch_errors"] = count_matches(_LAUNCH_ERR, results)
    facts["census"] = any(rx.search(results) for rx in _CENSUS)
    facts["claimed"] = claimed_count(said)

    # A census this turn is sufficient: the agent asked what is alive rather than assuming.
    if facts["census"]:
        return False, claims, facts

    # No census -- fall back to successful launches observed in this turn.
    if facts["launched"] < 1:
        return True, claims, facts

    # Launches happened, but the claim overstates them (the exact 2026-08-11 burn).
    if facts["claimed"] > facts["launched"]:
        return True, claims, facts

    return False, claims, facts


def turn(transcript_path: str) -> tuple[str, str, int]:
    """(assistant text this turn, concatenated tool-result text this turn, tool-call count).

    Mirrors evidence_with_claim.turn: a user entry with STRING content starts the turn; a
    list-shaped one is a tool result being fed back and stays INSIDE the turn.
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
        hook_log.record("inflight_claim_needs_census", trigger=trigger,
                        transcript_path=transcript, extra=dict(extra, event=event))
    except Exception:
        pass


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
    would_block, claims, facts = evaluate(said, results, calls)
    overridden = bool(OVERRIDE.search(said))

    if overridden:
        _log("overridden" if would_block else "preemptive",
             claims[0] if claims else "(no claim detected)", transcript, facts)
        return 0

    if not would_block:
        return 0

    shown = "\n".join(f"  [in-flight] ...{frag}..." for frag in claims[:3])
    detail = (f"  successful launches seen this turn: {facts['launched']}\n"
              f"  dispatch ERRORS seen this turn:     {facts['dispatch_errors']}\n"
              f"  count asserted in your text:        {facts['claimed'] or '(none stated)'}\n")
    reason = (
        "This turn tells the human that background work is IN FLIGHT, without a census "
        "backing it:\n\n" + shown + "\n\n" + detail + "\n"
        "On 2026-08-11 a batch of six Agent calls was dispatched; ONE launched and five "
        "returned 'You already have a ...' errors. The batch result was read as success and "
        "the human was told '3 background subagents still running'. None existed. He had to "
        "catch it himself -- 'confirm they're alive? i see nothing in background' -- and the "
        "time in between was spent waiting on work that was never coming.\n\n"
        "A dispatch ATTEMPT is not a dispatch. If dispatch errors are non-zero above, that is "
        "very likely what happened again.\n\n"
        "FIX: run a census before telling him what is alive -- `TaskList` is one call -- and "
        "report what it actually returned. A launch marker from THIS turn also satisfies this, "
        "but only up to the number actually launched.\n\n"
        "If the work is genuinely not verified alive, say so plainly ('those never started', "
        "'the dispatch errored') and the claim patterns stop matching. Override with "
        "`inflight:unverified`; its use is logged, including pre-emptive use."
    )
    _log("fire", claims[0], transcript, facts)
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

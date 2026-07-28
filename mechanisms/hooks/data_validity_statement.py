#!/usr/bin/env python3
"""Stop check: a quantitative comparison must state its comparability and its reach.

WHAT IT ASKS FOR, in the two terms that name it:

  * INTERNAL VALIDITY (comparability) -- do the compared groups differ ONLY in the thing
    being tested? Name what else varies: device, day, build, traffic mix, sample size,
    who was driving. A correct number over two non-comparable populations is not a
    finding, it is an artifact with a decimal point.
  * EXTERNAL VALIDITY (generalizability) -- what population, window and scenario does the
    claim cover? "On this device, this day" is a fine answer. Silence is not.

WHY IT EXISTS. On 2026-07-28 the conductor reported, with tables and correct arithmetic:
"p50 improved ~2.6s, confound excluded" (it was not excluded), and "the same device
dominates both sides" -- which was true of ALL turns and false of the SUBSET actually
being compared, where "before" was ~7 devices over two weeks and "after" was one device on
one day. Both numbers were right. Both conclusions were wrong, in the same way, twice in
one session, and the human caught both. Nothing in the measurement was at fault; the
missing sentence was.

This is the estate's own section 6h ("a contaminated control agrees with the treatment and
proves nothing -- name what it was blind to") applied one step later: to the analysis
rather than the control.

HONEST LIMIT, stated rather than implied (section 6g): this RAISES THE COST of omitting
the statement. It does not enforce a true one. `Validity:` followed by a sentence naming
both halves satisfies it, and a determined author can write a hollow sentence. What it
cannot be satisfied by is silence -- which is how both of the failures above happened.

Exit 0 always: this is a Stop-gate check, so it returns objections to stop_gate.py rather
than blocking a tool call itself.
"""
from __future__ import annotations

import json
import re
import sys

# ── trigger: a MEASUREMENT vocabulary AND a COMPARISON, both required ────────────────────────
# Both, deliberately. "443 passed, 0 failed" is two numbers and no measurement claim; "the
# page is 224,386 bytes" is a measurement and no comparison. Neither is a data analysis, and
# firing on them is how this check would get switched off in a week.
_MEASURE = re.compile(
    r"\b(p50|p95|p99|median|mean|average|percentile|baseline|sample size|n\s*=\s*\d+"
    r"|latency|throughput|duration_ms|distribution)\b", re.I)

_COMPARE = re.compile(
    r"\b(from\s+[\d.,]+\s*\w*\s+to\s+[\d.,]+"          # from X to Y
    r"|vs\.?|versus|against"
    r"|before\s+and\s+after|after\s+the\s+change|baseline"
    r"|improve\w*|reduc\w*|faster|slower|drop\w*|fell|rose|increase\w*|decrease\w*"
    r"|better|worse)\b", re.I)

# A bare number pair is not enough on its own; require at least two numerics in the vicinity
# of the comparison so a purely qualitative sentence ("this is better") does not trip it.
_TWO_NUMBERS = re.compile(r"[\d][\d.,]*\s*(ms|s\b|sec|%|x\b)?[^\n]{0,120}?[\d][\d.,]*", re.I)

# ── satisfaction: an explicit line naming BOTH halves ────────────────────────────────────────
# ANCHORED TO LINE START ON PURPOSE: this is a TEMPLATE, not a phrase to be detected.
# The first version accepted `Validity:` anywhere, to avoid "false-positiving on a legitimate
# inline form". Brad's correction (2026-07-28): if output needs templating to be testable,
# template it. A fixed shape the author must emit is mechanically checkable and unambiguous;
# a permissive matcher trying to recognise prose is neither, and every loosening of it is a
# hole. The required shape is a line of its own:
#     Validity: <what else differs between the groups> ... <what it does/does not cover>
_STATEMENT = re.compile(r"^\s*validity\s*:\s*(.+)$", re.I | re.M)

_INTERNAL_WORDS = re.compile(
    r"\b(confound\w*|comparab\w*|controlled|uncontrolled|same\s+device|different\s+devices?"
    r"|apples[- ]to[- ]apples|stratif\w*|sample|population|baseline\s+differs?|not\s+matched"
    r"|varies|varied|mix|window|build)\b", re.I)

_EXTERNAL_WORDS = re.compile(
    r"\b(generali[sz]\w*|does\s+not\s+extend|scoped?\s+to|only\s+covers?|beyond"
    r"|applies\s+only|this\s+device|that\s+window|cannot\s+be\s+extrapolat\w*"
    r"|uncorrelated|narrow\w*)\b", re.I)


def _strip_quoted(text: str) -> str:
    """Drop blockquotes and fenced code so quoting a report is not performing one."""
    out, fenced = [], False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or ln.lstrip().startswith(">"):
            continue
        out.append(ln)
    return "\n".join(out)


def evaluate(said: str) -> tuple[bool, list[tuple[str, str]]]:
    """(would_object, [(problem, fix)]). Pure, so the tests drive it without a transcript."""
    body = _strip_quoted(said or "")
    if not body.strip():
        return False, []

    if not (_MEASURE.search(body) and _COMPARE.search(body) and _TWO_NUMBERS.search(body)):
        return False, []

    m = _STATEMENT.search(body)
    if m:
        claim = m.group(1)
        # Both halves must actually be named. A bare "Validity: fine" is the token without
        # the thought, and the whole point is the thought.
        if _INTERNAL_WORDS.search(claim) and _EXTERNAL_WORDS.search(claim):
            return False, []
        missing = []
        if not _INTERNAL_WORDS.search(claim):
            missing.append("what ELSE differs between the compared groups (device, day, "
                           "build, traffic mix, sample size)")
        if not _EXTERNAL_WORDS.search(claim):
            missing.append("what the claim does and does NOT generalize to")
        return True, [(
            "A `Validity:` line is present but does not name both halves — missing: "
            + "; ".join(missing) + ".",
            "State comparability AND reach in that line. 'On one device across one day, "
            "against a baseline of seven devices over two weeks — device and build are "
            "confounded; does not generalize past that device.' is a complete answer.",
        )]

    return True, [(
        "This turn compares measurements without stating whether the compared data is "
        "COMPARABLE (internal validity) or how far the claim REACHES (external validity). "
        "Correct arithmetic over two non-comparable populations is an artifact with a "
        "decimal point — that failure happened twice in one session on 2026-07-28 and the "
        "human caught both.",
        "Add a line starting `Validity:` naming (a) what else differs between the groups "
        "besides the thing tested, and (b) what population/window the claim covers. If the "
        "comparison is not controlled, SAY SO and keep the number — a scoped finding beats "
        "a confident one.",
    )]


def turn(transcript_path: str) -> str:
    """The assistant's chat text for this turn (same reader shape as the sibling checks)."""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except Exception:
        return ""
    said: list[str] = []
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            e = json.loads(raw)
        except Exception:
            continue
        if e.get("type") == "user":
            break
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content") or []
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    said.append(part.get("text") or "")
    return "\n".join(reversed(said))


def _log(event: str, extra: dict, payload: dict) -> None:
    """Best-effort instrumentation; a dead metric must never take the check down."""
    try:
        import os
        import sys as _sys
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in _sys.path:
            _sys.path.insert(0, d)
        from hook_log import record
        record("data_validity_statement", trigger=event,
               transcript_path=(payload or {}).get("transcript_path"), extra=extra)
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    said = turn(payload.get("transcript_path") or "")
    objected, problems = evaluate(said)
    if not objected:
        return 0
    _log("fired", {"problems": [p for p, _ in problems]}, payload)
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for problem, fix in problems:
        print(f"  - {problem}\n    FIX: {fix}\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

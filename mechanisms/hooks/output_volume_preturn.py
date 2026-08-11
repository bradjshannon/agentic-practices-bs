#!/usr/bin/env python3
"""UserPromptSubmit hook: state my recent output volume BEFORE I write the next message.

WHY THIS EXISTS, AND WHY IT IS NOT output_budget.py
---------------------------------------------------
`output_budget.py` is a Stop hook. It measures correctly and it cannot work, and its own file
says so:

    "If volume climbs without the block, that is an argument for a different mechanism (one that
     acts BEFORE the message is emitted, which a Stop hook structurally cannot), not for
     restoring a remedy that costs double."

That prediction came true on 2026-07-26. The hook had been switched to advisory/silent on 07-24
because blocking made the operator read the over-long message and then its rewrite -- a guard for
reducing reading that doubled it. Silent, it recorded fires all night and changed nothing, and
The operator said:

    "okay, I'm already regressing to reading through pages and pages of your output in chat.
     can't do it, not sustainable, it's handcrafting instead of automating"

He is right that a promise to be brief is handcrafting. But so is a Stop hook here: by the time
Stop fires, the wall has been read. The only place a length control can act is BEFORE composition,
which is what UserPromptSubmit gets.

WHAT IT DOES
------------
Reads the transcript, measures the assistant's own text in the last few turns, and injects the
numbers. No verdict, no instruction -- just the measurement, in the same spirit as
`context-usage.py`: I cannot feel accumulated length any more than I can feel elapsed time, and a
number I am shown at the moment of composing is the cheapest possible intervention.

This is the "instrumented" enforcement class from the conductor brief -- the control lives in data
the agent already reads at the start of every turn, so it works on an agent that never read the
rule. It does not depend on remembering anything.

Deliberately NOT a block and NOT a nag: it prints one line when recent volume is over budget and
NOTHING when it is not. A reminder that fires every turn is one that gets skimmed, which is how
the prose version died.
"""
import json
import os
import sys

# MEASURE CUMULATIVE, NOT PER-MESSAGE. This is the correction that matters, and it was found by
# running the instrument and disbelieving its silence. Measured on the session where the operator said
# "pages and pages":
#     per-message : max 2,712 chars, only 3 of 120 messages over the 2,200 budget -- i.e. a
#                   per-message cap saw NOTHING WRONG
#     cumulative  : 54,037 chars across 121 messages, avg 446 -- about 18 pages
# The volume was in the COUNT, not the length. Every message was individually defensible, which
# is precisely why a per-message control cannot see this failure and why output_budget.py's own
# note called cumulative "the more honest measure of his reading load".
#
# So: budget the reading load per SITTING -- everything since he last spoke -- because that is
# the pile he actually faces when he comes back.
SINCE_BUDGET = 6000   # chars of my prose since the operator last spoke
SESSION_NOTE = 30000  # session total worth mentioning once it is this large


def _volume(path: str) -> tuple[int, int, int, int]:
    """(since_human, since_msgs, session_total, session_msgs) of MY OWN chat text.

    Tool calls and results excluded -- this counts only what the operator has to read. A user entry
    containing a tool_result is not him speaking and does not reset the sitting.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return 0, 0, 0, 0
    since = since_n = total = total_n = 0
    for e in entries:
        c = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and isinstance(c, list):
            n = sum(len(b.get("text") or "") for b in c
                    if isinstance(b, dict) and b.get("type") == "text")
            if n:
                since += n; since_n += 1; total += n; total_n += 1
        elif e.get("type") == "user":
            if isinstance(c, str) and c.strip():
                since = since_n = 0
            elif isinstance(c, list):
                kinds = {b.get("type") for b in c if isinstance(b, dict)}
                if "tool_result" not in kinds:
                    said = " ".join(b.get("text") or "" for b in c
                                    if isinstance(b, dict) and b.get("type") == "text")
                    if said.strip():
                        since = since_n = 0
    return since, since_n, total, total_n


def _assistant_message_lengths(path: str) -> list[int]:
    """Character counts of the assistant's own TEXT blocks, one entry per message.

    Tool calls and tool results are excluded: this measures what the operator has to READ.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return []
    out = []
    for e in entries:
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        n = sum(len(b.get("text") or "") for b in content
                if isinstance(b, dict) and b.get("type") == "text")
        if n:
            out.append(n)
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    path = payload.get("transcript_path") or ""
    if not path or not os.path.exists(path):
        return 0

    since, since_n, total, total_n = _volume(path)

    # Silent when there is nothing to say. A line every turn trains skimming, which is how the
    # prose version of this rule died.
    if since <= SINCE_BUDGET and total <= SESSION_NOTE:
        return 0

    bits = []
    if since > SINCE_BUDGET:
        bits.append(f"{since:,} chars in {since_n} messages since the operator last spoke "
                    f"(budget {SINCE_BUDGET:,})")
    if total > SESSION_NOTE:
        bits.append(f"{total:,} chars this session across {total_n} messages "
                    f"(~{total // 3000} pages)")
    print("[output volume] " + "; ".join(bits) + ". "
          "The volume is usually in the COUNT, not the length — fewer messages, not shorter ones. "
          "Detail belongs on the status page or in a commit, where it is greppable; chat gets "
          "what changed / what needs him / what's next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

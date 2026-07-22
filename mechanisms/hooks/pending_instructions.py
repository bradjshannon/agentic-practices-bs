#!/usr/bin/env python3
"""SessionStart hook: put Brad's OUTSTANDING INSTRUCTIONS in context at turn 0.

WHY THIS IS A HOOK AND NOT A LINE IN THE BRIEF
----------------------------------------------
On 2026-07-22 a conductor ran an entire session without seeing two explicit instructions Brad
had left for it. They were not lost -- they were sitting in `iotta-firmware/docs/needs-you.md`,
written deliberately by the previous run's handoff. The conductor read `decisions.md`,
`TODO.md` and the cold read (the three the brief names as required) and skipped that one.
Brad had to ask "did you do that?" for it to surface.

The same run also found three unhandled feedback items in `conductor-inbox.jsonl` -- Brad
answering questions through the status page's own reply box -- **by accident**, because the
file showed up as untracked in a `git status` run for an unrelated reason. Nothing polled it.

Two independent channels from the human to the agent, both write-only in practice. The fix
that was reached for first was to add a line to the brief telling the next conductor to read
the file. That is hand-crafting: it works only on an agent that read the brief, remembered the
line, and chose to act on it -- and the brief ALREADY said to read `needs-you.md`, in step 0.
A rule that has failed once is a rule, not a mechanism.

So this fires without the agent's participation and cannot be satisfied except by actually
delivering the content: SessionStart stdout is injected into the session's context, so the
instructions are simply *there*, before the first tool call, whether or not the agent knows
this file exists.

WHAT IT DOES
------------
Emits, compactly:
  * every `handled: false` entry in `docs/conductor-inbox.jsonl` (the status-page reply box)
  * the instruction-bearing sections of `docs/needs-you.md`

It is deliberately a POINTER plus enough text to act on, not a paste of the whole file: the
point is that the agent cannot fail to know these exist. Reading the full file is still on it.

FAIL-QUIET, NOT FAIL-SILENT
---------------------------
If a source is missing or unreadable this says so, in one line, rather than printing nothing.
A hook whose empty output is indistinguishable from "no pending instructions" would be the
exact null-vs-instrument-failure trap this project keeps paying for.
"""
import json
import os
import sys

FW = os.path.expanduser("~/Documents/GitHub/iotta-firmware")
INBOX = os.path.join(FW, "docs", "conductor-inbox.jsonl")
NEEDS = os.path.join(FW, "docs", "needs-you.md")

# Headings in needs-you.md that carry INSTRUCTIONS (things to do) rather than decisions
# awaiting Brad. Matched case-insensitively as substrings.
INSTRUCTION_MARKERS = ("next run", "you said", "asap", "only you can do")
MAX_ITEMS = 12


def unhandled_inbox() -> tuple[list, str | None]:
    if not os.path.exists(INBOX):
        return [], f"{INBOX} not present"
    rows, bad = [], 0
    try:
        with open(INBOX, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    bad += 1
                    continue
                if isinstance(e, dict) and not e.get("handled"):
                    rows.append(e)
    except Exception as exc:
        return [], f"could not read inbox: {exc}"
    note = f"({bad} malformed line(s) skipped)" if bad else None
    return rows, note


def instruction_sections() -> tuple[list, str | None]:
    if not os.path.exists(NEEDS):
        return [], f"{NEEDS} not present"
    try:
        lines = open(NEEDS, encoding="utf-8", errors="replace").read().splitlines()
    except Exception as exc:
        return [], f"could not read needs-you.md: {exc}"
    out, cur = [], None
    for ln in lines:
        if ln.startswith("#"):
            title = ln.lstrip("#").strip()
            keep = any(m in title.lower() for m in INSTRUCTION_MARKERS)
            cur = {"title": title, "body": []} if keep else None
            if cur:
                out.append(cur)
        elif cur is not None and ln.strip():
            cur["body"].append(ln.strip())
    return out, None


def main() -> int:
    inbox, inote = unhandled_inbox()
    sections, snote = instruction_sections()

    if not inbox and not sections and not inote and not snote:
        return 0  # genuinely nothing pending -- stay quiet

    print("=== PENDING INSTRUCTIONS FROM BRAD (injected by pending_instructions.py) ===")
    print("These are UNREAD/UNHANDLED items from the two channels he uses to instruct a run.")
    print("They are not optional background. Read the source files before planning the run.\n")

    print(f"-- Status-page feedback, unhandled: {len(inbox)}  [{INBOX}] --")
    if inote:
        print(f"   !! {inote}")
    for e in inbox[:MAX_ITEMS]:
        sel = " / ".join(str(s) for s in (e.get("selected") or [])) or "-"
        txt = (e.get("text") or "").replace("\n", " ")
        print(f"   [{str(e.get('ts'))[:19]}] item={e.get('item_id')} answer={sel}")
        if txt:
            print(f"        text: {txt[:300]}")
    if len(inbox) > MAX_ITEMS:
        print(f"   ... and {len(inbox) - MAX_ITEMS} more")

    print(f"\n-- Instruction sections in needs-you.md: {len(sections)}  [{NEEDS}] --")
    if snote:
        print(f"   !! {snote}")
    for s in sections:
        print(f"   ## {s['title']}")
        for b in s["body"][:6]:
            print(f"      {b[:200]}")
        if len(s["body"]) > 6:
            print(f"      ... ({len(s['body']) - 6} more lines -- READ THE FILE)")
    print("=== end pending instructions ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

GH = os.path.expanduser("~/Documents/GitHub")
COND = os.path.join(GH, "conductor-bs", "conductors", "iotta")
INBOX = os.path.join(COND, "inbox.jsonl")
NEEDS = os.path.join(COND, "needs-you.md")

# Standing guidance that priming MUST cover. Brad, 2026-07-22: "Does priming include reading the
# docs in conductor-bs and agentic best practices? It needs to."
#
# Listed as an INDEX, not pasted: the point is that a conductor cannot fail to know these exist
# or which one is relevant. Pasting them would blow out turn 0 and train skimming — the same
# volume failure the output budget exists to fight.
#
# Why here rather than as a line in the brief: the brief ALREADY said to pull the practices repo,
# and a run still primed without it, because a doc instructing you to read another doc is the
# Voluntary class. This fires whether or not the brief is read.
# The list itself lives in the REPO, not here: `conductor-bs/PRIMING.md`. Brad, 2026-07-22:
# "maybe just say to read all the docs in given folders, or all the docs listed in a given file,
# so it's easy to update in the future."
#
# That indirection is the point. Changing what gets primed is then a one-line edit to a markdown
# file, from either machine, with no hook change and no code review — and it propagates to every
# machine that pulls the repo. A hardcoded list here would be a second place for the same
# knowledge to live, i.e. a thing that drifts.
MANIFEST = os.path.join(GH, "conductor-bs", "PRIMING.md")

# Used only if the manifest is unreachable, so a missing repo degrades to something rather than
# silently priming on nothing.
FALLBACK_DIRS = [
    ("conductor-bs/tactics", "conductor tactics (both machines)"),
    ("agentic-practices-bs/lessons", "portable failure-earned lessons"),
    ("agentic-practices-bs/mechanisms", "mechanisms catalogue"),
]


def _parse_manifest() -> tuple[list[tuple[str, str]], list[tuple[str, str]], str | None]:
    """(dirs, files, note) from PRIMING.md's fenced ```primed-dirs / ```primed-files blocks."""
    if not os.path.exists(MANIFEST):
        return FALLBACK_DIRS, [], f"{MANIFEST} MISSING — using a built-in fallback list, which " \
                                  "may be out of date. Clone conductor-bs."
    try:
        text = open(MANIFEST, encoding="utf-8", errors="replace").read()
    except Exception as exc:
        return FALLBACK_DIRS, [], f"could not read {MANIFEST}: {exc}"
    out = {"primed-dirs": [], "primed-files": []}
    for key in out:
        marker = "```" + key
        if marker not in text:
            continue
        body = text.split(marker, 1)[1].split("```", 1)[0]
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            path, _, label = line.partition(" ")
            out[key].append((path, label.strip() or "(no label)"))
    if not out["primed-dirs"] and not out["primed-files"]:
        return FALLBACK_DIRS, [], f"{MANIFEST} parsed to NOTHING — check its fenced blocks"
    return out["primed-dirs"], out["primed-files"], None

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


def guidance_index() -> tuple[list[tuple[str, list[str], str | None]], list[str], str | None]:
    """(dir entries, named files, manifest note)."""
    dirs, files, note = _parse_manifest()
    out = []
    for rel, label in dirs:
        path = os.path.join(GH, rel.replace("/", os.sep))
        if not os.path.isdir(path):
            out.append((f"{rel} — {label}", [],
                        "DIRECTORY MISSING — clone the repo; do not proceed as if it were empty"))
            continue
        try:
            names = sorted(f for f in os.listdir(path) if f.endswith(".md"))
        except Exception as exc:
            out.append((f"{rel} — {label}", [], f"unreadable: {exc}"))
            continue
        out.append((f"{rel} — {label}", names, None if names else "empty (suspicious)"))
    named = []
    for rel, label in files:
        exists = os.path.exists(os.path.join(GH, rel.replace("/", os.sep)))
        named.append(f"{'   ' if exists else '!! MISSING '}{rel} — {label}")
    return out, named, note


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
    dir_entries, named, mnote = guidance_index()
    print("\n-- STANDING GUIDANCE — priming MUST cover these (`git pull` both repos first) --")
    print("   (manifest: conductor-bs/PRIMING.md — edit THAT to change what is primed)")
    if mnote:
        print(f"   !! {mnote}")
    for label, files, note in dir_entries:
        print(f"   {label}:")
        if note:
            print(f"      !! {note}")
        for f in files:
            print(f"      - {f}")
    if named:
        print("   named files:")
        for n in named:
            print(f"   {n}")
    print("   Read the ones relevant to what you are about to do. They are short, they are")
    print("   failure-earned, and every one exists because something went wrong without it.")
    print("=== end pending instructions ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

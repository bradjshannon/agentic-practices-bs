#!/usr/bin/env python3
"""SessionStart hook: put the operator's OUTSTANDING INSTRUCTIONS in context at turn 0.

WHY THIS IS A HOOK AND NOT A LINE IN THE BRIEF
----------------------------------------------
On 2026-07-22 a conductor ran an entire session without seeing two explicit instructions the operator
had left for it. They were not lost -- they were sitting in `myproject-firmware/docs/needs-you.md`,
written deliberately by the previous run's handoff. The conductor read `decisions.md`,
`TODO.md` and the cold read (the three the brief names as required) and skipped that one.
The operator had to ask "did you do that?" for it to surface.

The same run also found three unhandled feedback items in `conductor-inbox.jsonl` -- the operator
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
COND = os.path.join(GH, "conductor-bs", "conductors", "myproject")
INBOX = os.path.join(COND, "inbox.jsonl")
NEEDS = os.path.join(COND, "needs-you.md")
# The page generator, loaded only for `stale_report()` -- see stale_instructions() below.
GEN = os.path.join(GH, "conductor-bs", "tools", "conductor-status.py")

# Standing guidance that priming MUST cover. The operator, 2026-07-22: "Does priming include reading the
# docs in conductor-bs and agentic best practices? It needs to."
#
# Listed as an INDEX, not pasted: the point is that a conductor cannot fail to know these exist
# or which one is relevant. Pasting them would blow out turn 0 and train skimming — the same
# volume failure the output budget exists to fight.
#
# Why here rather than as a line in the brief: the brief ALREADY said to pull the practices repo,
# and a run still primed without it, because a doc instructing you to read another doc is the
# Voluntary class. This fires whether or not the brief is read.
# The list itself lives in the REPO, not here: `conductor-bs/PRIMING.md`. The operator, 2026-07-22:
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
# awaiting the operator. Matched case-insensitively as substrings.
INSTRUCTION_MARKERS = ("next run", "you said", "asap", "only you can do")
MAX_ITEMS = 12


_conductor_status_mod = None  # cache: loaded once per hook run, both callers need it


def _load_conductor_status():
    """Load conductor-status.py by path, the way this hook always has -- but with its own
    directory on sys.path first.

    ── WHY THIS EXISTS (2026-08-06) ──────────────────────────────────────────────────────────
    `6a60974` (conductor-bs) extracted `conductor_render_core.py` as a sibling module in
    `tools/`, imported from `conductor-status.py` as a bare `import conductor_render_core`.
    That works when the script is run normally (`python conductor-status.py`) because Python
    puts the script's own directory at `sys.path[0]`. It silently breaks under
    `importlib.util.spec_from_file_location` + `module_from_spec`, which does NOT touch
    `sys.path` -- so every load-by-path caller (this hook's two of them) started raising
    `ModuleNotFoundError: No module named 'conductor_render_core'` the moment that commit
    landed, and both failures were swallowed by their `except Exception` and reported as
    generic "could not ..." notes. Reads exactly like staleness; it is a load-path bug.
    Reproduced directly: `python -c "importlib.util.spec_from_file_location(...); exec_module"`
    raises the ModuleNotFoundError; `python conductor-status.py --help` (cwd=tools/) does not.
    """
    global _conductor_status_mod
    if _conductor_status_mod is not None:
        return _conductor_status_mod
    import importlib.util
    tools_dir = os.path.dirname(GEN)
    added = tools_dir not in sys.path
    if added:
        sys.path.insert(0, tools_dir)
    try:
        spec = importlib.util.spec_from_file_location("conductor_status_for_hook", GEN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if added:
            sys.path.remove(tools_dir)
    _conductor_status_mod = mod
    return mod


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


def split_unhandled(rows: list) -> tuple[list, list, str | None]:
    """`(asks, done_acks, note)` — a question is an obligation, a Done ack is a fact.

    The operator, 2026-07-29: *"i need a 'done' button for simple tasks you give me like 'run this cmd',
    so you don't have to parse tokens for an ack"*. That button appends an ordinary inbox row with
    `selected: ["__done__"]`, so WITHOUT this split it would land in the list above headed *"UNREAD
    /UNHANDLED items ... not optional background"* — i.e. every command he finished would read as
    an unanswered question. A button that inflates that list is worse than no button.

    THE RULE LIVES IN THE REPO (`classify_unhandled()` in tools/conductor-status.py), same
    delegation as `stale_cards()` below and for the same reason: the repo syncs on a `git pull`,
    a hook file does not, and a second copy of the rule is a thing that drifts. If the generator
    cannot be loaded this degrades to "everything is an ask" and SAYS SO — over-reporting is the
    safe direction here, and a silent degrade would look exactly like "he never pressed Done".
    """
    if not os.path.exists(GEN):
        return rows, [], f"{GEN} MISSING — cannot separate Done acks from questions; all rows " \
                         "below are listed as asks. Clone conductor-bs."
    try:
        mod = _load_conductor_status()
        asks, dones = mod.classify_unhandled(rows)
        return asks, dones, None
    except Exception as exc:
        return rows, [], f"could not classify Done acks ({exc}); all rows listed as asks"


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


def stale_cards() -> tuple[str, str | None]:
    """The conductor's own stale-pinned-card report, for turn 0. `(report, note)`.

    ── WHY THIS IS HERE (2026-07-28) ─────────────────────────────────────────────────────────
    The operator: *"i'm sick of seeing the stale card warning. that warning should be delivered to YOU"*.
    His page used to carry a red "N STALE CARDS" strip above everything he had to decide. Staleness
    is a defect in the CONDUCTOR's bookkeeping -- a card written before his last message and never
    reconciled -- so showing it to him converted my unfinished work into a chore for him, on the one
    surface built to spend less of his attention. It was removed from the page and redirected here.

    HERE, and not "a line in the brief telling the conductor to check", for the same reason this
    whole file exists: per conductors/myproject/brief.md's enforcement table, a control that requires
    remembering is the Voluntary class and decays. SessionStart stdout lands in context before the
    first tool call, so the run knows whether it is serving him stale cards whether or not it ever
    heard of this check.

    THE WORDING AND THE VERDICT LIVE IN THE REPO (`stale_report()` in tools/conductor-status.py),
    not here. This is a ~15-line delegation on purpose: the repo syncs across both machines on a
    `git pull`, a hook file does not, and a second copy of the logic is a thing that drifts.
    """
    if not os.path.exists(GEN):
        return "", f"{GEN} MISSING — cannot check for stale cards. Clone conductor-bs."
    try:
        mod = _load_conductor_status()
        return mod.stale_report(), None
    except Exception as exc:
        # FAIL-QUIET, NOT FAIL-SILENT (see the module docstring): an empty report and a broken
        # importer must not look the same, or "no stale cards" becomes a thing that is never true
        # and never false.
        return "", f"could not run the stale-card report: {exc}"


def _size_tag(path: str) -> str:
    """Rough token cost of opening this file, as `21k` / `<1k` / `?`.

    ── WHY A SIZE SITS BESIDE EVERY INDEXED FILENAME (2026-08-20) ────────────────────────────
    The index exists so a run can decide WHICH file to open. Until now a ```primed-dirs``` entry
    rendered as a bare filename, so the one fact that decides that -- what the read costs -- was
    the one fact absent. `decisions.md` (11k) and `decisions-archive.md` (359k) appeared as two
    indistinguishable lines; so did `STATUS-digest.md` (<1k) and `STATUS.md` (93k).

    That is not a priming-volume problem, which is the smallest lever there is
    (`agentic-practices-bs/lessons/priming-reduction-is-the-weakest-of-four-levers-2026-08-20.md`
    ranks it 4th of 4). It is a TOOL-RESULT-VOLUME problem, which is lever #2: a misdirected read
    of a 359k-token archive is not a one-time cost, it is re-read by every later request in the
    session. The whole annotation added here costs ~500 tokens once and defends against that.

    Estimated as bytes/4 and labelled as an estimate. Derived from the file on disk, so it cannot
    drift the way a hand-written "(large)" note would -- nobody has to remember to update it.
    """
    try:
        n = os.path.getsize(path) // 4
    except OSError:
        return "?"
    return f"{n // 1000}k" if n >= 1000 else "<1k"


def guidance_index() -> tuple[list[tuple[str, list[str], str | None]], list[str], str | None]:
    """(dir entries, named files, manifest note).

    A ```primed-files``` entry whose path falls INSIDE a ```primed-dirs``` directory is rendered
    on that directory's own line (marked `>`), not repeated in the trailing "named files" block.
    Two reasons, both measured: the label was landing ~100 lines away from the filename it
    describes, where it could not inform the read decision it exists for; and the brief, the
    needs-you file and the hardware-facts file were each being printed twice.

    This is also how the manifest now expresses "indexed, but do NOT read this one" -- a labelled
    entry rather than an exclusion. See PRIMING.md's Rules for why exclusion was rejected: an
    exclude list and a split directory both move membership from automatic to remembered, and
    hiding a hazardous file also hides the warning from the run that finds it with `ls` anyway.
    """
    dirs, files, note = _parse_manifest()
    labels = {rel.replace("\\", "/"): label for rel, label in files}
    claimed: set[str] = set()
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
        rows = []
        width = min(max((len(n) for n in names), default=0), 44)
        for n in names:
            key = f"{rel.rstrip('/')}/{n}"
            flabel = labels.get(key)
            if flabel:
                claimed.add(key)
            mark = ">" if flabel else "-"
            row = f"{mark} {n.ljust(width)} {_size_tag(os.path.join(path, n)).rjust(5)}"
            rows.append(f"{row}  {flabel}" if flabel else row)
        out.append((f"{rel} — {label}", rows, None if names else "empty (suspicious)"))
    named = []
    for rel, label in files:
        if rel.replace("\\", "/") in claimed:
            continue  # already shown, with this label, on its directory's line above
        full = os.path.join(GH, rel.replace("/", os.sep))
        exists = os.path.exists(full)
        size = f" [{_size_tag(full)}]" if exists else ""
        named.append(f"{'   ' if exists else '!! MISSING '}{rel}{size} — {label}")
    return out, named, note


def print_guidance() -> None:
    """The standing-guidance index. Printed on EVERY session, unconditionally.

    It used to sit at the tail of main(), below an early return taken whenever the inbox,
    instruction sections and stale cards were all empty -- so a block believed to be Structural
    was in fact coupled to unrelated state. Measured 2026-08-10 across the hook's whole lifetime:
    it reached 57 of 923 sessions, 6.2%. Every "it is in PRIMING.md, so the next agent gets it"
    claim rested on this, and 93.8% of the time nobody got anything.
    """
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
            print(f"      {f}")
    if named:
        print("   named files (outside the folders above):")
        for n in named:
            print(f"   {n}")
    print("   Sizes are ESTIMATED token cost (bytes/4) — they are what the read will cost you,")
    print("   not a ranking. `>` marks a file the manifest labels; read its label before opening.")
    print("   Read the ones relevant to what you are about to do. They are short, they are")
    print("   failure-earned, and every one exists because something went wrong without it.")


def main() -> int:
    inbox, inote = unhandled_inbox()
    sections, snote = instruction_sections()
    stale, stnote = stale_cards()

    if not inbox and not sections and not inote and not snote and not stale and not stnote:
        # Nothing pending -- stay quiet about the INBOX, but still deliver the guidance index.
        print_guidance()
        return 0

    print("=== PENDING INSTRUCTIONS FROM THE OPERATOR (injected by pending_instructions.py) ===")
    print("These are UNREAD/UNHANDLED items from the two channels he uses to instruct a run.")
    print("They are not optional background. Read the source files before planning the run.\n")

    asks, dones, dnote = split_unhandled(inbox)

    print(f"-- Status-page feedback, unhandled: {len(asks)}  [{INBOX}] --")
    if inote:
        print(f"   !! {inote}")
    if dnote:
        print(f"   !! {dnote}")
    for e in asks[:MAX_ITEMS]:
        sel = " / ".join(str(s) for s in (e.get("selected") or [])) or "-"
        txt = (e.get("text") or "").replace("\n", " ")
        # The `id` is printed because it is the handle every tool now takes (`ack-inbox.py --id`,
        # the page's supersede field). The timestamp stays for human orientation, but it is NOT an
        # identity: at whole-second resolution two messages sent in the same second shared one.
        # A row written before ids existed says so rather than showing a blank.
        print(f"   [{str(e.get('ts'))[:19]}] id={e.get('id') or '(pre-id row)'} "
              f"item={e.get('item_id')} answer={sel}")
        if txt:
            print(f"        text: {txt[:300]}")
    if len(asks) > MAX_ITEMS:
        print(f"   ... and {len(asks) - MAX_ITEMS} more")

    # Separate heading, and NOT under "unhandled items ... not optional background": these are
    # things he FINISHED, not things he is waiting on. Still printed, and still un-acked, because
    # "he ran the command you asked for" is usually the input the next step needs -- ack them with
    # `tools/ack-inbox.py --id <id>` once you have used them.
    if dones:
        print(f"\n-- He pressed DONE on {len(dones)} item(s) — tasks he COMPLETED, not questions --")
        for e in dones[:MAX_ITEMS]:
            txt = (e.get("text") or "").replace("\n", " ")
            print(f"   [{str(e.get('ts'))[:19]}] id={e.get('id') or '(pre-id row)'} "
                  f"item={e.get('item_id')} DONE" + (f" — note: {txt[:200]}" if txt else ""))
        if len(dones) > MAX_ITEMS:
            print(f"   ... and {len(dones) - MAX_ITEMS} more")

    print(f"\n-- Instruction sections in needs-you.md: {len(sections)}  [{NEEDS}] --")
    if snote:
        print(f"   !! {snote}")
    for s in sections:
        print(f"   ## {s['title']}")
        for b in s["body"][:6]:
            print(f"      {b[:200]}")
        if len(s["body"]) > 6:
            print(f"      ... ({len(s['body']) - 6} more lines -- READ THE FILE)")
    # YOUR OWN BOOKKEEPING, not his. Printed here rather than on his page (see stale_cards()).
    if stale or stnote:
        print("\n-- Your stale pinned cards (NOT shown to the operator — this is yours to fix) --")
        if stnote:
            print(f"   !! {stnote}")
        for line in (stale or "").splitlines():
            print(f"   {line}")

    print_guidance()
    print("=== end pending instructions ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

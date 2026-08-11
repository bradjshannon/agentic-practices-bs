#!/usr/bin/env python3
"""Tests for the inbox-surfacing piece of pacer_announce.py (_new_inbox_lines / _entry_key).

The operator's complaint: decisions entered on the status page mid-run sat unread until the next
session's SessionStart hook. The fix piggybacks on the existing pacer-fire heartbeat. The load-
bearing behaviors tested here: unhandled entries surface, handled entries don't, an entry once
surfaced is never repeated (no nagging), and a later NEW entry still gets through after that.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pacer_announce as pa  # noqa: E402


def _write_inbox(path, entries):
    with open(path, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"      got:  {got}")
        print(f"      want: {want}")
    return ok


results = []

with tempfile.TemporaryDirectory() as td:
    inbox = os.path.join(td, "inbox.jsonl")
    state = os.path.join(td, "surfaced.json")

    e1 = {"ts": "2026-07-23T10:00:00", "item_id": "d1", "selected": ["yes"],
          "text": "ship it", "handled": False}
    e2 = {"ts": "2026-07-23T10:05:00", "item_id": "d2", "selected": ["no"],
          "text": "hold off", "handled": False}
    e_handled = {"ts": "2026-07-23T09:00:00", "item_id": "d0", "selected": ["ack"],
                 "text": "already dealt with", "handled": True}

    # --- run 1: 2 unhandled + 1 handled seeded -----------------------------------------------
    _write_inbox(inbox, [e_handled, e1, e2])
    lines1 = pa._new_inbox_lines(inbox_path=inbox, state_path=state)
    results.append(check("run1: both unhandled entries emitted",
                          len(lines1), 2))
    results.append(check("run1: item d1 present", any("d1" in ln for ln in lines1), True))
    results.append(check("run1: item d2 present", any("d2" in ln for ln in lines1), True))
    results.append(check("run1: handled item d0 NOT emitted",
                          any("d0" in ln for ln in lines1), False))
    results.append(check("run1: state file written", os.path.exists(state), True))

    # --- run 2: identical inbox, re-run -> nothing new (dedup, no nagging) -------------------
    lines2 = pa._new_inbox_lines(inbox_path=inbox, state_path=state)
    results.append(check("run2: no re-emission of already-surfaced entries",
                          lines2, []))

    # --- run 3: add a genuinely new 3rd unhandled entry -> only it emits ---------------------
    e3 = {"ts": "2026-07-23T10:10:00", "item_id": "d3", "selected": [],
          "text": "third decision", "handled": False}
    _write_inbox(inbox, [e_handled, e1, e2, e3])
    lines3 = pa._new_inbox_lines(inbox_path=inbox, state_path=state)
    results.append(check("run3: only the new entry (d3) emitted", len(lines3), 1))
    results.append(check("run3: it is d3", "d3" in lines3[0] if lines3 else False, True))

    # --- an entry that flips handled:true later simply stops being eligible ------------------
    e2_now_handled = dict(e2, handled=True)
    _write_inbox(inbox, [e_handled, e1, e2_now_handled, e3])
    lines4 = pa._new_inbox_lines(inbox_path=inbox, state_path=state)
    results.append(check("run4: nothing new (d2 now handled, d3 already surfaced)",
                          lines4, []))

    # --- fail-open: missing inbox file -> [] not an exception ---------------------------------
    missing = os.path.join(td, "does-not-exist.jsonl")
    results.append(check("missing inbox file -> [] (fail-open)",
                          pa._new_inbox_lines(inbox_path=missing, state_path=state), []))

    # --- fail-open: malformed JSON line is skipped, valid lines still processed --------------
    bad_inbox = os.path.join(td, "bad.jsonl")
    with open(bad_inbox, "w", encoding="utf-8") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps({"ts": "x", "item_id": "d9", "text": "ok", "handled": False}) + "\n")
    fresh_state = os.path.join(td, "fresh_state.json")
    lines5 = pa._new_inbox_lines(inbox_path=bad_inbox, state_path=fresh_state)
    results.append(check("malformed line skipped, valid line still emitted",
                          len(lines5), 1))

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

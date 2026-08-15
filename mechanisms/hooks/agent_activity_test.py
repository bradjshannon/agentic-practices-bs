#!/usr/bin/env python3
"""Falsifiers for agent_activity.py.

The load-bearing case is `POSITIVE CONTROL: the silent case is reportable at all` — this whole
mechanism exists to name an agent that has made zero tool calls, so a suite that only checks
live agents render would pass while the headline case was broken. Every "it did not report X"
assertion below is paired with one proving X CAN be reported.

Loads the module SITTING NEXT TO THIS FILE, never whichever copy is installed.

Run: python mechanisms/hooks/agent_activity_test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Telemetry isolation -- keep this suite OUT of the live ~/.claude/hook-events.jsonl, the
# one file that says whether a hook works. Must be set before any hook runs; subprocesses
# inherit it. Any new hook test needs these two lines. See hook_log.log_path().
os.environ["HOOK_LOG_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hooklog-test-"), "events.jsonl")


HOOK = Path(__file__).with_name("agent_activity.py")
_spec = importlib.util.spec_from_file_location("agent_activity", HOOK)
m = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(m)

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


NOW = datetime(2026, 8, 9, 12, 0, 0)


def line_for(aid, lines):
    return next((ln for ln in lines if aid in ln), "")


# --- the headline case: dispatched, zero tool calls ----------------------------------------
dispatched = [{"agentId": "aDEAD", "description": "decode coredumps",
               "at": (NOW - timedelta(minutes=41)).isoformat(timespec="seconds")}]
lines = m.summary_lines("s", now=NOW, dispatched=dispatched, acts={})
check("POSITIVE CONTROL: the silent case is reportable at all", any("aDEAD" in ln for ln in lines))
check("HEADLINE: an agent with no tool calls says so explicitly",
      "NO TOOL CALLS SINCE DISPATCH" in line_for("aDEAD", lines))
check("HEADLINE: and it reports how long it has been silent",
      "41m" in line_for("aDEAD", lines))
check("HEADLINE: the header counts the silent ones", "1 with no tool calls" in lines[0])

# --- the live case, and it must NOT be reported as silent ----------------------------------
acts = {"aLIVE": {"last": (NOW - timedelta(seconds=20)).isoformat(timespec="seconds"),
                  "n": 12, "tool": "Bash"}}
dispatched2 = [{"agentId": "aLIVE", "description": "build and flash",
                "at": (NOW - timedelta(minutes=9)).isoformat(timespec="seconds")}]
lines2 = m.summary_lines("s", now=NOW, dispatched=dispatched2, acts=acts)
check("LIVE: a working agent is not called silent",
      "NO TOOL CALLS" not in line_for("aLIVE", lines2))
check("LIVE: it reports age and call count", "20s" in line_for("aLIVE", lines2)
      and "12 calls" in line_for("aLIVE", lines2))
check("LIVE: header reports zero silent", "0 with no tool calls" in lines2[0])
check("LIVE: not flagged stale", "stale" not in line_for("aLIVE", lines2))

# --- the CONTROL that matters: both in one reading -----------------------------------------
both = m.summary_lines("s", now=NOW, dispatched=dispatched + dispatched2, acts=acts)
check("CONTROL: silent and live render differently in the SAME reading",
      "NO TOOL CALLS" in line_for("aDEAD", both) and "NO TOOL CALLS" not in line_for("aLIVE", both))
check("CONTROL: header counts exactly one silent of two", "2 dispatched, 1 with no tool calls" in both[0])

# --- staleness is flagged but distinguished from silence -----------------------------------
stale = {"aSTALE": {"last": (NOW - timedelta(minutes=30)).isoformat(timespec="seconds"),
                    "n": 3, "tool": "Bash"}}
ls = m.summary_lines("s", now=NOW, dispatched=[{"agentId": "aSTALE", "description": "long build",
                                                "at": NOW.isoformat()}], acts=stale)
check("STALE: an old marker is flagged", "stale" in line_for("aSTALE", ls))
check("STALE: but is NOT reported as having made no calls",
      "NO TOOL CALLS" not in line_for("aSTALE", ls))

# --- the honesty line must always ride along ------------------------------------------------
check("every reading carries the 'not progress' caveat",
      any("NOT progress" in ln for ln in both))

# --- nothing dispatched -> say nothing, not a scary empty header ----------------------------
check("no dispatched agents -> no output at all", m.summary_lines("s", now=NOW, dispatched=[], acts={}) == [])

# --- timezone trap: aware UTC and naive local must not be subtracted raw ---------------------
aware = m.parse_stamp("2026-08-09T16:00:00+00:00")
naive = m.parse_stamp("2026-08-09T16:00:00")
check("TZ: an aware UTC stamp is converted to local wall time", aware is not None and aware.tzinfo is None)
check("TZ: a naive stamp is taken as local unchanged", naive == datetime(2026, 8, 9, 16, 0, 0))
check("TZ: the two are NOT treated as the same instant unless the box is UTC",
      (aware == naive) == (datetime.now().astimezone().utcoffset() == timedelta(0)))
check("TZ: garbage parses to None rather than raising", m.parse_stamp("not-a-date") is None
      and m.parse_stamp(None) is None)

# --- collector: bounded growth is the whole volume claim -------------------------------------
d = Path(tempfile.mkdtemp())
os.environ["AGENT_ACTIVITY_STATE_DIR"] = str(d)
for i in range(50):
    m.record_call("sess", "aX", "Bash")
for i in range(10):
    m.record_call("sess", "aY", "Read")
state = json.loads((d / "agent-activity-sess.json").read_text(encoding="utf-8"))
check("VOLUME: 60 calls from 2 agents produce exactly 2 entries", len(state) == 2)
check("VOLUME: the call count is a counter inside the entry", state["aX"]["n"] == 50 and state["aY"]["n"] == 10)
check("COLLECT: the last tool is recorded", state["aY"]["tool"] == "Read")
m.record_call("sess", None, "Bash")
check("COLLECT: a top-level call (no agent_id) writes nothing",
      len(json.loads((d / "agent-activity-sess.json").read_text(encoding="utf-8"))) == 2)

# --- fallback source: reads agent_id rows out of the shared event log -------------------------
log = d / "events.jsonl"
os.environ["AGENT_ACTIVITY_EVENT_LOG"] = str(log)
rows = [
    {"ts": "2026-08-09T15:00:00+00:00", "hook": "tool_output_volume", "tool": "Bash", "agent_id": "aLOG"},
    {"ts": "2026-08-09T15:00:30+00:00", "hook": "tool_output_volume", "tool": "PowerShell", "agent_id": "aLOG"},
    {"ts": "2026-08-09T15:00:31+00:00", "hook": "tool_output_volume", "tool": "Bash"},  # top-level
    {"not": "json-with-agent_id-but-no-id", "agent_id": ""},
]
log.write_text("\n".join(json.dumps(r) for r in rows) + "\nNOT JSON AT ALL\n", encoding="utf-8")
fb = m.from_event_log()
check("FALLBACK: agent rows are picked up from the event log", "aLOG" in fb and fb["aLOG"]["n"] == 2)
check("FALLBACK: a row with no agent_id is ignored", len(fb) == 1)
check("FALLBACK: the newest stamp wins", fb["aLOG"]["last"] == "2026-08-09T15:00:30+00:00")
check("FALLBACK: a malformed line does not kill the read", isinstance(fb, dict))
log.write_text("", encoding="utf-8")
check("FALLBACK: an empty log yields {} rather than raising", m.from_event_log() == {})
os.environ["AGENT_ACTIVITY_EVENT_LOG"] = str(d / "does-not-exist.jsonl")
check("FALLBACK: a missing log yields {} (fail-open)", m.from_event_log() == {})

# --- the hook half must never block, whatever it is fed ---------------------------------------
def run_hook(stdin_text):
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text,
                          capture_output=True, text=True, timeout=30)


env_note = ""
for name, payload in [
    ("valid PostToolUse", json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                      "agent_id": "aZ", "session_id": "s"})),
    ("malformed json", "not json at all"),
    ("empty stdin", ""),
    ("null fields", json.dumps({"hook_event_name": "PostToolUse", "tool_name": None,
                                "agent_id": None, "session_id": None})),
    ("wrong event", json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                "agent_id": "aZ"})),
    ("unexpected shape", json.dumps({"hook_event_name": "PostToolUse", "agent_id": {"a": 1}})),
]:
    p = run_hook(payload)
    check(f"FAIL-OPEN: {name} -> exit 0, no stdout{env_note}",
          p.returncode == 0 and p.stdout.strip() == "")

# --- --status must not explode on a machine with no state -------------------------------------
os.environ["AGENT_ACTIVITY_STATE_DIR"] = str(d / "empty-dir")
p = subprocess.run([sys.executable, str(HOOK), "--status"], capture_output=True, text=True, timeout=30)
check("CLI: --status on an empty state dir exits 0", p.returncode == 0)

print()
bad = [n for n, ok in results if not ok]
print(f"{len(results)} checks ran")
print("ALL PASS" if not bad else f"FAILURES ({len(bad)}): " + "; ".join(bad))
sys.exit(0 if not bad else 1)

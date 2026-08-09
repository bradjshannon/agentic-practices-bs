#!/usr/bin/env python3
"""Per-agent tool-call marker — is a dispatched subagent dead, stuck, or working?

THE REQUIREMENT. A conductor that dispatches a subagent has exactly one channel back: the
final message. So "died at dispatch", "wedged", and "doing a nine-minute build" are
indistinguishable from outside. That cost one run 4h 08m on 2026-07-31, during which the
conductor also held a bogus constraint on the dead agent's behalf.

WHY A TOOL-CALL MARKER AND NOT A HEARTBEAT TICKER. The first design was a timestamp file
written every few seconds by a process the agent backgrounds as its first act, on the theory
that absence means the process tree died. **Measured 2026-08-09, and it is false.** A probe
agent finished normally at 21:52:39; its backgrounded shell was still writing at 22:00:17 —
7m38s later, 128 ticks, no decay — and stopped only when the PIDs were killed by hand. Left
alone it would have run its full loop. The cause is structural, not a harness bug: every tool
shell in a session is a child of ONE shared process, so a subagent has no process tree of its
own for its children to be orphaned from, and the harness performs no reaping at agent-stop.
A ticker therefore cannot mean "dead", and a signal whose absence means nothing is worse than
none because it reads as reassurance.

This design takes the opposite trade DELIBERATELY: **only the agent itself can cause a tool
call, so a marker written from its own calls cannot lie about liveness.** Nothing else can
write it on the agent's behalf.

    | signal                        | absence means                                    |
    |-------------------------------|--------------------------------------------------|
    | marker never written at all   | the agent has made ZERO tool calls since dispatch |
    | marker present but stale       | *weak* — see the blindness paragraph below        |

**THE CASE THIS IS FOR is the first row**, and it is the one that cost 4h 08m. An agent that
died at dispatch emits nothing, and "no marker has ever existed for this agentId" is
unambiguous in a way ticker-absence never was.

HONEST LIMITS — read these before trusting a reading.

  * **Blind during a long foreground call.** A ten-minute build produces no tool calls, so a
    working agent and a wedged agent look identical for those ten minutes. This is the exact
    blindness the ticker was invented to cover, and it is accepted here because it is the
    BENIGN state: the agent is doing what it was asked. Treat mid-run staleness as a weak
    secondary signal, never as proof of a stall, and never kill on it alone.
  * **A pulse is not a report.** Frequent tool calls prove an agent is executing, not that it
    is doing the right thing or making progress. It can loop. Do not let a healthy marker talk
    you out of reading the agent's actual result — that failure mode is why the milestone half
    of the original design existed.
  * **Coverage is only as broad as what is wired** (see INSTALL). With the fallback source
    alone, an agent doing only Read/Grep/Edit looks silent while working. Wiring the collector
    on all tools closes this; until then a stale reading is even weaker than the paragraph
    above says.
  * **Absence of a registry row is not absence of an agent.** The join below is against
    revive_before_dispatch.py's per-session registry; an agent dispatched in another session,
    or before that hook was installed, has no row and will not appear at all.

TWO SOURCES, ONE READER, AND WHY.

  1. **Primary — `~/.claude/state/agent-activity-<session>.json`**, written by this file's own
     PostToolUse half. An in-place dict, ONE ENTRY PER agent_id: `{last, n, tool}`.
  2. **Fallback — the tail of `~/.claude/hook-events.jsonl`**, filtered to rows carrying
     `agent_id`. This needs no new wiring and works today, because `tool_output_volume.py` is
     already registered PostToolUse and already records `agent_id` per call. Its coverage is
     Bash/PowerShell only.

The reader merges both and takes the most recent evidence from either, so the surface degrades
gracefully rather than going blank when the collector is not wired.

VOLUME — an instrument that degrades what it observes is its own failure mode, so:

  * **Write cost per tool call:** one read + one atomic replace of a small JSON file (a few
    hundred bytes for a typical fan-out). Not an append to the shared event log — deliberately.
    Adding one `hook-events.jsonl` line per tool call across all tools would multiply a file
    that is already ~8.4k lines by several times a day, which is the degradation this
    paragraph exists to prevent.
  * **What bounds the state file:** the number of DISTINCT AGENTS in a session, not the number
    of tool calls. A thousand calls from six agents is six entries. `n` is a counter inside the
    entry, so it costs no growth.
  * **Reader cost:** the fallback reads only the LAST `TAIL_BYTES` of the event log, so its
    cost is constant no matter how large that file becomes.

TIMEZONE TRAP, handled explicitly because mixing these silently produces plausible wrong ages.
`revive_before_dispatch.py`'s registry writes `at` via `time.strftime` — **naive LOCAL time**.
`hook_log.py` writes `ts` as **aware UTC**. This module normalises naive stamps as local and
aware stamps as-is before any subtraction. Getting this wrong on a UTC-4 box yields ages off by
exactly four hours, in the direction that makes a live agent look long dead.

FAIL-OPEN, unconditionally. This fires on EVERY tool call of every agent, which makes it the
most dangerous file in this directory to get wrong. Every path swallows its own errors and the
hook half always exits 0. A reading that is missing is correct behaviour; a tool call this hook
blocked is not.

INSTALL
  Collector — PostToolUse, matcher ".*" (ALL tools; a narrower matcher narrows coverage exactly
  as the limits above describe). NOT WIRED as of this writing: it is a new hook firing on every
  tool call on a shared machine, which is the operator's call, not an agent's. The reader works
  without it via the fallback source.

    {"matcher": ".*", "hooks": [{"type": "command", "timeout": 10,
      "command": "py -3 -c \\"import runpy,os;runpy.run_path(os.path.expanduser('~/.claude/hooks/agent_activity.py'),run_name='__main__')\\""}]}

  Reader — one call added to pacer_announce.py, which already injects into the conductor's own
  context on a pacer fire. That placement is the point: a CLI nobody remembers to run is
  Voluntary class, and this whole mechanism exists because a conductor did not notice something.

  Status CLI (secondary, for a human):
    python ~/.claude/hooks/agent_activity.py --status
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

TAIL_BYTES = 400_000
STALE_AFTER = 600  # seconds; a marker older than this is CALLED OUT, never acted on alone


def _state_dir() -> str:
    # Env seam for tests: a module-level constant cannot be patched after runpy.run_path()
    # returns a copy of the module globals, the same reasoning estate_tracker.py documents.
    return os.environ.get("AGENT_ACTIVITY_STATE_DIR") or os.path.expanduser("~/.claude/state")


def _event_log() -> str:
    return os.environ.get("AGENT_ACTIVITY_EVENT_LOG") or os.path.expanduser(
        "~/.claude/hook-events.jsonl")


def _safe(session_id) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")


def _state_path(session_id) -> str:
    return os.path.join(_state_dir(), f"agent-activity-{_safe(session_id)}.json")


def _registry_path(session_id) -> str:
    return os.path.join(_state_dir(), f"agent-registry-{_safe(session_id)}.json")


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def parse_stamp(text):
    """ISO stamp -> naive LOCAL datetime, or None. See the TIMEZONE TRAP note in the docstring.

    An aware stamp is converted to local wall time; a naive one is assumed already local. Both
    end up in the same frame so a subtraction between them is meaningful.
    """
    if not isinstance(text, str) or not text:
        return None
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


# --------------------------------------------------------------------------- collector half

def record_call(session_id, agent_id, tool):
    """Update this agent's entry in place. Bounded by distinct agents, never by call count."""
    if not agent_id:
        return  # top-level actor: it has its own channel and needs no marker
    path = _state_path(session_id)
    state = _load_json(path, {})
    entry = state.get(agent_id) if isinstance(state.get(agent_id), dict) else {}
    state[agent_id] = {
        "last": datetime.now().isoformat(timespec="seconds"),
        "n": int(entry.get("n") or 0) + 1,
        "tool": tool or entry.get("tool") or "?",
    }
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, path)
    except OSError:
        pass


# --------------------------------------------------------------------------- reader half

def from_event_log(path=None):
    """Fallback marker source: {agent_id: {last, n, tool}} from the TAIL of the shared log.

    Constant-cost regardless of how large that file grows -- it seeks to the last TAIL_BYTES
    and discards the first (probably partial) line.
    """
    path = path or _event_log()
    out = {}
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as fh:
            if size > TAIL_BYTES:
                fh.seek(size - TAIL_BYTES)
                fh.readline()
            for line in fh:
                if "agent_id" not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                aid = row.get("agent_id")
                if not isinstance(aid, str) or not aid:
                    continue
                cur = out.setdefault(aid, {"last": None, "n": 0, "tool": "?"})
                cur["n"] += 1
                ts = row.get("ts")
                if isinstance(ts, str) and (cur["last"] is None or ts > cur["last"]):
                    cur["last"] = ts
                    cur["tool"] = row.get("tool") or row.get("hook") or "?"
    except (OSError, ValueError):
        return {}
    return out


def activity(session_id):
    """Merge both sources, newest evidence wins per agent."""
    merged = {}
    for src in (from_event_log(), _load_json(_state_path(session_id), {})):
        if not isinstance(src, dict):
            continue
        for aid, rec in src.items():
            if not isinstance(rec, dict):
                continue
            prev = merged.get(aid)
            a, b = parse_stamp(rec.get("last")), parse_stamp((prev or {}).get("last"))
            if prev is None or (a and (b is None or a > b)):
                merged[aid] = {"last": rec.get("last"),
                               "n": int(rec.get("n") or 0) + (int(prev.get("n") or 0) if prev else 0),
                               "tool": rec.get("tool") or "?"}
            elif prev:
                prev["n"] = int(prev.get("n") or 0) + int(rec.get("n") or 0)
    return merged


def _age(dt, now):
    secs = max(0, int((now - dt).total_seconds()))
    if secs < 90:
        return f"{secs}s"
    if secs < 5400:
        return f"{secs // 60}m"
    return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"


def summary_lines(session_id, now=None, dispatched=None, acts=None):
    """One line per dispatched agent. Empty list when there is nothing to say.

    `dispatched` / `acts` are injectable so a test can drive this without touching real state.
    """
    now = now or datetime.now()
    if dispatched is None:
        reg = _load_json(_registry_path(session_id), {})
        dispatched = []
        for subtype, rows in (reg or {}).items():
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict) and r.get("agentId"):
                        dispatched.append({**r, "subagent_type": subtype})
    if acts is None:
        acts = activity(session_id)
    if not dispatched:
        return []

    lines, silent = [], 0
    for row in dispatched:
        aid = row.get("agentId")
        desc = (row.get("description") or "")[:34]
        rec = acts.get(aid)
        last = parse_stamp((rec or {}).get("last"))
        if last is None:
            at = parse_stamp(row.get("at"))
            since = f", dispatched {_age(at, now)} ago" if at else ""
            lines.append(f"  {aid}  {desc!r}  NO TOOL CALLS SINCE DISPATCH{since}")
            silent += 1
        else:
            age = _age(last, now)
            flag = "  <- stale, may be in a long call" if (now - last).total_seconds() > STALE_AFTER else ""
            lines.append(f"  {aid}  {desc!r}  last call {age} ago ({rec.get('n')} calls, "
                         f"{rec.get('tool')}){flag}")
    if not lines:
        return []
    head = f"[subagent activity — {len(lines)} dispatched, {silent} with no tool calls]"
    return [head, *lines,
            "  A marker proves execution, NOT progress: read the agent's result, not this line."]


# --------------------------------------------------------------------------- entry points

def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return sys.exit(0)
    try:
        if (payload.get("hook_event_name") or "") != "PostToolUse":
            return sys.exit(0)
        record_call(payload.get("session_id"), payload.get("agent_id"),
                    payload.get("tool_name"))
    except Exception:  # noqa: BLE001 -- fail-open is the contract; this fires on EVERY tool call
        pass
    return sys.exit(0)


def _cli():
    session = None
    argv = sys.argv[1:]
    if "--session" in argv:
        session = argv[argv.index("--session") + 1]
    if session is None:
        # Newest registry in the state dir -- the session most likely to be live.
        try:
            regs = [f for f in os.listdir(_state_dir()) if f.startswith("agent-registry-")]
            regs.sort(key=lambda f: os.path.getmtime(os.path.join(_state_dir(), f)))
            session = regs[-1][len("agent-registry-"):-len(".json")] if regs else None
        except OSError:
            session = None
    lines = summary_lines(session)
    print(f"session: {session}")
    print("\n".join(lines) if lines else "  (no dispatched agents on record)")
    return 0


if __name__ == "__main__":
    if "--status" in sys.argv:
        sys.exit(_cli())
    main()

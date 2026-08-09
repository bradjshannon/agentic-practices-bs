#!/usr/bin/env python3
"""UserPromptSubmit hook: on a pacer FIRE, inject the heartbeat line directly into context.

Brad, 2026-07-22/23: on every pacer fire, the agent should surface — in chat — the current ET
time, context %, and the status-page link. The voluntary version (agent reads the pacer's output
file and relays it) decayed to ZERO: across an entire session the agent never once announced,
because nothing forced it.

Proven feasible 2026-07-23 with `ups_probe.py`: `UserPromptSubmit` DOES fire on the
task-notification a background pacer completion delivers, and the payload carries
`transcript_path` (needed for context %). A UserPromptSubmit hook's stdout is injected into the
model's context — so this reaches the agent with no action on its part. That is the structural
form the four-times-repeated prose rule could not be.

FIRES ONLY on a fresh pacer fire — gated on `pacer-armed.json`'s `fires_at` having just gone
past, deduped by that exact `fires_at`, and bounded to a 120 s window. So it does NOT inject on
Brad's normal messages, on unrelated background completions, or twice for one fire.
"""
import hashlib
import json
import os
import runpy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE = Path.home() / ".claude" / "pacer-armed.json"
SEEN = Path.home() / ".claude" / ".pacer-announced"

# Brad, 2026-07-23: the status page lets him drop new decisions into the inbox MID-RUN, but
# SessionStart (pending_instructions.py) only reads it at turn 0 -- anything entered after that
# sits unread until the next session. This hook already fires every ~7 min on the pacer's
# background completion and is already injected into context (see module docstring), so it is
# the natural place to also surface new inbox entries: no new wake-up mechanism needed, just
# piggyback on the one that exists.
#
# Same inbox pending_instructions.py reads at turn 0 -- hardcoded to the iotta conductor's inbox
# to match that hook, not parameterized over CONDUCTOR_ROOTS (which also covers conductor-bs and
# iotta-firmware): there is exactly one status-page inbox today and generalizing it before a
# second one exists would be speculative.
INBOX = Path.home() / "Documents" / "GitHub" / "conductor-bs" / "conductors" / "iotta" / "inbox.jsonl"
# Dedup state for the inbox surfacing below -- separate from SEEN (which dedups the heartbeat
# line itself by fires_at). Keyed per-entry (see _entry_key), not per-fire, so an entry surfaced
# once stays surfaced across every later pacer fire even though fires_at keeps changing.
INBOX_SURFACED = Path.home() / ".claude" / "conductor-inbox-surfaced.json"
# The status-page link is per-machine AND per-conductor (video uses :9443, the server conductor
# uses :8787, and the tailnet host differs on workpc). So it is NOT hardcoded: turn-pacer.py reads
# the CONDUCTOR_STATUS_URL env var when it arms and stamps it into pacer-armed.json, which this hook
# reads below. Fallbacks: the env var directly (in case an older pacer-armed.json lacks the field),
# then this last-resort default (this machine's).
DEFAULT_LINK = "https://video.tail54e284.ts.net:9443/"

# Only enforce in conductor sessions (same scoping as pacer_armed.py) — a pacer armed from an
# unrelated project should not inject a conductor heartbeat.
_HOME = os.path.expanduser("~")
CONDUCTOR_ROOTS = [
    os.path.join(_HOME, "Documents", "GitHub", "conductor-bs"),
    os.path.join(_HOME, "Documents", "GitHub", "iotta-bs"),
    os.path.join(_HOME, "Documents", "GitHub", "iotta-firmware"),
]


def _context_pct() -> float | None:
    """Reuse turn-pacer.py's own context% computation — one definition, cannot drift.

    run_path executes the module but does NOT call its main() (run_name != '__main__'), so this
    just imports the function; no sleep, no arming.
    """
    try:
        cu = runpy.run_path(str(Path.home() / ".claude" / "turn-pacer.py"))
        return cu["_context_pct"]()
    except Exception:
        return None


def _entry_key(e: dict) -> str:
    """Stable identity for a dedup entry: the entry's own `id` when it has one.

    Every inbox entry has carried an `id` since 2026-07-27 (see conductor-status.py's entry_id and
    tools/migrate_inbox_ids.py). Before that this composed one out of ts + item_id + a hash of the
    text, because `ts` at whole-second resolution was not an identity -- two messages sent in the
    same second shared it. The composite remains as _legacy_entry_key for rows written by an older
    tool, and so that the dedup state file written under the old scheme is still honoured (see
    _new_inbox_lines) instead of re-announcing everything once.
    """
    stored = e.get("id")
    if isinstance(stored, str) and stored:
        return stored
    return _legacy_entry_key(e)


def _legacy_entry_key(e: dict) -> str:
    """The pre-id composite. Read-only compatibility: still recognised in the state file, never
    written for a row that has a real id."""
    text_hash = hashlib.sha256((e.get("text") or "").encode("utf-8", "replace")).hexdigest()[:12]
    return f"{e.get('ts')}|{e.get('item_id')}|{text_hash}"


def _new_inbox_lines(inbox_path=INBOX, state_path=INBOX_SURFACED) -> list[str]:
    """Unhandled inbox entries not yet surfaced by this mechanism, formatted for injection.

    Read-only w.r.t. the inbox itself (never touches `handled` -- that's a consume action owned
    elsewhere, per the brief). Mutates only the dedup state file, to remember what it has already
    shown. An entry that later flips handled:true simply stops being eligible (it's filtered by
    the `not e.get("handled")` check below on every call, dedup state or not).

    Fail-open: any error (missing file, bad JSON, unwritable state dir) yields an empty list
    rather than raising -- this must never break the pacer heartbeat it rides along with.
    """
    try:
        inbox_path = Path(inbox_path)
        if not inbox_path.exists():
            return []
        entries = []
        with open(inbox_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if isinstance(e, dict) and not e.get("handled"):
                    entries.append(e)
        if not entries:
            return []

        state_path = Path(state_path)
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}

        lines, newly_surfaced = [], False
        for e in entries:
            key = _entry_key(e)
            # The legacy composite is checked too, so the switch to ids does not re-announce every
            # unhandled entry once. Self-retiring: only the new key is ever written.
            if key in state or _legacy_entry_key(e) in state:
                continue
            # DO NOT SURFACE THE TEXT BODY HERE. Brad's own fix, 2026-07-26:
            #   "i would suggest having the hook NOT provide a preview of the data, except maybe an
            #    identifier or timestamp, and instead provide the command you should use for the
            #    complete read."
            # This used to emit txt[:200] with NO ellipsis and no length, so a clipped message was
            # indistinguishable from a complete one. A conductor read a 347-char message that
            # appeared to stop mid-sentence, concluded the page had sent it early, wrote that into a
            # commit message, and rebuilt a working key handler around a data-loss event that never
            # happened. The wrong lesson would be "truncate more visibly"; the right one is that a
            # partial copy of the source should not be in the pipeline at all when the full read is
            # one command away.
            # `selected` IS surfaced in full -- a chip is a complete value, not an excerpt of one.
            sel = " / ".join(str(s) for s in (e.get("selected") or [])) or "-"
            txt = e.get("text") or ""
            body = f"text: {len(txt)} chars NOT SHOWN — read it" if txt else "no text"
            # The id, not just the timestamp: it is the handle `ack-inbox.py --id` takes, and it
            # names ONE message where a whole-second timestamp could name two.
            lines.append(f"{str(e.get('ts', ''))[:19]}  id={e.get('id') or '(pre-id row)'}  "
                         f"item={e.get('item_id')}  selected=[{sel}]  {body}")
            state[key] = True
            newly_surfaced = True

        if newly_surfaced:
            try:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(state), encoding="utf-8")
            except Exception:
                pass
        return lines
    except Exception:
        return []


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # Read the armed pacer. If it hasn't fired (fires_at in the future) or the state is
    # unreadable, do nothing — this is a normal message, not a fire.
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
        fires_at = str(st.get("fires_at", ""))
        cwd = os.path.normpath(st.get("cwd", ""))
        when = datetime.fromisoformat(fires_at)
    except Exception:
        return 0

    link = st.get("status_url") or os.environ.get("CONDUCTOR_STATUS_URL") or DEFAULT_LINK

    if not any(cwd.startswith(os.path.normpath(r)) for r in CONDUCTOR_ROOTS):
        return 0  # pacer armed outside a conductor repo — not our heartbeat

    # ── Brad's inbox is surfaced on EVERY wake, NOT only on a pacer fire ──────────────────
    # Brad, 2026-07-24: "you're not picking up the stuff i do on the status page,
    # automatically." He was right, and the cost was measured: SEVEN entries he typed into the
    # Ask boxes between 00:24 and 00:38 never reached the run. Every wake in that window was a
    # subagent completion or one of his own chat messages — and the inbox scan used to live
    # BELOW the pacer-fire gate (the `delta` checks), so none of them scanned it.
    #
    # The gate was never load-bearing for the inbox: `_new_inbox_lines()` dedups PER ENTRY via
    # INBOX_SURFACED, so running it on every prompt surfaces each entry exactly once regardless
    # of what woke us. Coupling it to the pacer bought nothing and silently dropped his input.
    #
    # The heartbeat line below stays gated — it is a statement about elapsed time and only
    # means anything on an actual fire. These are two different signals that were sharing one
    # trigger; that was the defect.
    early_inbox = _new_inbox_lines()
    if early_inbox:
        # The pointer, not the payload. Emitting the exact command is the whole point: a conductor
        # that never read this file cannot act on a preview it was not given, so the only path
        # forward is the complete read.
        n = len(early_inbox)
        print("\n".join([
            "[new status-page input from Brad — bodies NOT included by design]",
            *early_inbox,
            "",
            f"READ THE FULL TEXT before acting on any of it ({n} new). PowerShell, any directory:",
            "  python ~/Documents/GitHub/conductor-bs/tools/ack-inbox.py "
            f"--read {max(n, 4)}",
            "  # complete text, nothing truncated. Add --unhandled for only what is unacked.",
        ]))

    now = datetime.now(timezone.utc)
    delta = (now - when).total_seconds()
    # The waking notification IS the pacer's own completion, arriving ~at fires_at. But fires_at is
    # stored truncated to whole seconds, and the sleep can complete a fraction before it, so a bare
    # `when > now` read "not fired yet" and dropped the announce (observed 2026-07-23). Grace of
    # 15 s absorbs that edge. A normal message / unrelated task lands far outside this window
    # (fires_at minutes away) and is correctly ignored; dedup stops any double-announce.
    if delta < -15:
        return 0  # fire is still >15 s away — a normal message or an unrelated completion
    if delta > 120:
        return 0  # a long-past fire — don't announce it on some later unrelated prompt

    # Dedup: announce each distinct fires_at exactly once.
    try:
        if SEEN.exists() and SEEN.read_text(encoding="utf-8").strip() == fires_at:
            return 0
    except Exception:
        pass
    try:
        SEEN.write_text(fires_at, encoding="utf-8")
    except Exception:
        pass

    et = now - timedelta(hours=4)  # EDT
    ctx = _context_pct()
    ctx_s = f"context {ctx:.0f}%" if ctx is not None else "context unknown"
    line = f"{et.strftime('%I:%M %p ET')} · {ctx_s} · {link}"
    # UserPromptSubmit stdout → injected into context. Phrased as an instruction to relay, so the
    # agent posts the measured line rather than paraphrasing (and a fabricated figure would be
    # visibly inconsistent with this one).
    out = [f"[pacer heartbeat — post this line VERBATIM as the first line of your reply]\n{line}"]

    # Subagent liveness — NOW DONE HERE (2026-08-09), by a route the NOTE below did not consider.
    # That note rejected transcript SIZE+MTIME and was right to. A later design, an OS-clock
    # ticker backgrounded by the agent, was also built-and-rejected: MEASURED, a probe agent's
    # backgrounded shell kept writing for 7m38s after the agent finished and stopped only when
    # killed by hand, because every tool shell in a session is a child of ONE shared process and
    # the harness reaps nothing at agent-stop. Ticker-absence therefore means nothing.
    # What survives: a marker written from the agent's OWN tool calls. Only the agent can cause
    # one, so it cannot lie about liveness. Injected here rather than left to a CLI because a
    # reader nobody remembers to run is Voluntary class, and this exists because a conductor did
    # not notice a dead agent for 4h08m. Its blind spot (a long foreground call) and its weakness
    # (a pulse is not progress) are documented in agent_activity.py and stated in its own output.
    # Fail-open in its own right: a break here must not cost the heartbeat line above.
    try:
        import runpy as _runpy
        _aa = _runpy.run_path(str(Path.home() / ".claude" / "hooks" / "agent_activity.py"))
        out.extend(_aa["summary_lines"](payload.get("session_id")) or [])
    except Exception:
        pass

    # HISTORICAL NOTE — why the SIZE+MTIME version was rejected. Kept because the measurement
    # is still true and still rules that approach out.
    # Brad, 2026-07-31: "you should check these things on pacer fire, for subagents", after a
    # dispatched agent sat dead for 4h08m while the conductor enforced constraints on its behalf.
    # The proposed tell was transcript SIZE + MTIME. It does not work: MEASURED the same hour,
    # every a<id>.output file in the session tasks dir is 0 bytes -- including agents that had
    # completed successfully with full reports, and one running at that moment. The harness does
    # not stream to that file, so "0 bytes" flags everything and the guard would cry wolf on every
    # fire. This codebase's own doctrine is that a check with false positives gets bypassed and
    # takes its true positives with it.
    # What ACTUALLY established death was `TaskStop` on the id: it errors on an unknown id and
    # lists the agents that ARE running. That is a model-tool call, not something a hook can make,
    # so the reconciliation is prompted below rather than performed here.


    # NOTE: the inbox surfacing that used to live here has moved ABOVE the pacer-fire gate (see
    # the block after the CONDUCTOR_ROOTS check). Anything new was already printed on the way in,
    # on this and every other wake. Do NOT re-add a scan here — _new_inbox_lines() marks entries
    # surfaced, so a second call in the same invocation returns nothing and would read as "no new
    # input from Brad", which is exactly the silent-drop this hook exists to prevent.
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

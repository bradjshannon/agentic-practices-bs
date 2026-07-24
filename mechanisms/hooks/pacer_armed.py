#!/usr/bin/env python3
"""Stop hook: a turn may not end with nothing scheduled to wake this run.

THE FAILURE THIS IS BUILT FROM (2026-07-22, measured, not estimated)
--------------------------------------------------------------------
The run went **idle for 7.1 hours** — 04:02 → 11:09 ET — and neither the agent nor Brad
noticed until Brad asked what had been accomplished. There was no crash and nothing wedged.
The last pacer completed at 03:21 and **none was armed after it**, so when Brad stopped
messaging there was simply nothing left that could re-invoke the agent. An agent is only
woken by a human message or a background task completing; with both absent, the run is over
without ever saying so.

**The shape is the point, and it is not carelessness.** Arming got dropped *precisely while
Brad was actively messaging* — his replies were doing the waking, so re-arming felt redundant
every single turn. The mechanism was abandoned exactly when it was about to become the only
thing that could wake the run. Any control whose perceived value is lowest right before it is
needed cannot be left to judgement; that is the definition of the Voluntary class, and the
brief already says that class decays. It decayed here after being explicitly documented as
"the backstop for the yield-and-stall failure."

WHY A STOP HOOK AND NOT A BETTER HABIT
--------------------------------------
A hook cannot arm the pacer itself: what re-invokes the agent is the completion of a
background task the *agent* created, so the arming call has to come from the agent. What a
hook CAN do is refuse to let the turn end without one. That converts "remember to re-arm"
into "the turn does not end until you have," which works on an agent that never read this.

HOW "ARMED" IS ESTABLISHED
--------------------------
`turn-pacer.py` writes `~/.claude/pacer-armed.json` with a `fires_at` timestamp when it starts.
This hook reads it and asks one question: **is `fires_at` in the future?**

That is deliberately a timestamp rather than a flag or a lock file, so a stale breadcrumb
cannot fake being armed — a pacer that already fired, or was killed, leaves `fires_at` in the
past, which reads as NOT armed. The loop is: fire → unarmed → blocked at the next turn end →
re-armed. Nothing to clean up, and no state that can rot into a false positive.

WHEN IT IS RIGHT TO END UNARMED — `pacer:none`
----------------------------------------------
Ending the run deliberately (wind-down complete, work genuinely finished, Brad said stop) is a
legitimate unarmed end, and the token says so. Its use is LOGGED, including pre-emptive use, so
if this hook decays into a formality that shows up as data instead of as a hunch — the same
audit the other hooks now carry, built after three of them were found being satisfied in form.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

STATE = os.path.expanduser("~/.claude/pacer-armed.json")
OVERRIDE = re.compile(r"pacer:\s*none\b", re.I)

# Repo roots where the conductor runs — enforcement is scoped to these.
# Checked as path prefixes against the cwd written by turn-pacer.py when it arms.
# A pacer armed in an unrelated project does NOT count as armed for a conductor session,
# and a conductor-less session does NOT need a pacer at all.
_HOME = os.path.expanduser("~")
CONDUCTOR_ROOTS = [
    os.path.join(_HOME, "Documents", "GitHub", "conductor-bs"),
    os.path.join(_HOME, "Documents", "GitHub", "iotta-bs"),
    os.path.join(_HOME, "Documents", "GitHub", "iotta-firmware"),
]


def _in_conductor_context() -> bool:
    """Return True if the currently armed pacer was launched from a conductor repo."""
    try:
        with open(STATE, encoding="utf-8") as fh:
            cwd = json.load(fh).get("cwd", "")
    except Exception:
        return False  # no state file → no conductor session active
    cwd = os.path.normpath(cwd)
    return any(cwd.startswith(os.path.normpath(r)) for r in CONDUCTOR_ROOTS)


def _pid_alive(pid: int) -> bool:
    """Is that process actually still there? Best-effort and FAIL-OPEN: if we cannot tell, we
    say yes, because wrongly declaring a live pacer dead would block every turn end."""
    if not pid:
        return True  # older breadcrumb without a pid — cannot check, do not punish
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode != 0:
                return True  # cannot tell
            return str(int(pid)) in (out.stdout or "")
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True  # cannot tell -> assume alive


def armed_for() -> float | None:
    """Seconds until the pacer fires, or None if nothing is armed.

    ⚠️ `fires_at` ALONE IS NOT ENOUGH, and the docstring above this file used to claim it was
    ("a pacer that already fired, or was killed, leaves `fires_at` in the past"). That is false
    for a KILLED pacer: the breadcrumb is written when the pacer starts, with `fires_at` set in
    the future, and nothing removes it if the process dies before firing. Measured 2026-07-24 at
    wind-down — three pacers were killed mid-sleep, `pacer-armed.json` still named a future
    `fires_at` and pid 6856, and that pid was gone (verified against a positive control: the
    same query saw 7 live python processes and its own pid).

    That is a FALSE ALLOW in the direction that matters: this hook exists to stop a turn ending
    with nothing scheduled to wake the run, and it was doing the opposite — certifying a dead
    pacer as armed. The cost of the failure it guards is already on record: a 7.1-hour silent
    idle on 2026-07-22.

    So the timestamp is now corroborated against the recorded pid. Fail-open on any uncertainty,
    because a false DENY blocks every turn end and would get the guard disabled outright, taking
    its true positives with it.
    """
    try:
        with open(STATE, encoding="utf-8") as fh:
            state = json.load(fh)
        fires_at = datetime.fromisoformat(state["fires_at"])
    except Exception:
        return None
    delta = (fires_at - datetime.now(timezone.utc)).total_seconds()
    if delta <= 0:
        return None
    if not _pid_alive(state.get("pid") or 0):
        return None  # breadcrumb says armed, process is gone -> nothing will wake this run
    return delta


def turn_text(transcript_path: str) -> str:
    """The assistant's text this turn — where an override token (`pacer:none`) would be.

    Delegates to the shared window so the turn boundary excludes machine notifications; the
    old local scan started the window at any string-content user entry, including a
    <task-notification>, and read the wrong text for the token.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from turn_window import turn as _turn
        return _turn(transcript_path)["said"]
    except Exception:
        return ""


def _log(event: str, trigger: str, transcript: str) -> None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("pacer_armed", trigger=trigger, transcript_path=transcript,
                        extra={"event": event})
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("stop_hook_active"):
        return 0

    # Only enforce in conductor sessions. If the state file's cwd is not under a
    # conductor repo (or has no cwd field yet), this session doesn't need a pacer.
    if not _in_conductor_context():
        return 0

    transcript = payload.get("transcript_path") or ""
    text = turn_text(transcript) if transcript and os.path.exists(transcript) else ""
    remaining = armed_for()

    if OVERRIDE.search(text):
        _log("overridden" if remaining is None else "preemptive",
             f"{remaining if remaining else 0:.0f}s remaining", transcript)
        return 0

    if remaining is not None:
        return 0  # something will wake this run

    reason = (
        "NOTHING IS SCHEDULED TO WAKE THIS RUN — the turn cannot end here.\n\n"
        "You are re-invoked by exactly two things: a message from Brad, or a background task "
        "completing. If neither is pending, ending this turn ends the run silently — no crash, "
        "no notice. That happened on 2026-07-22: the run sat idle 7.1 hours (04:02-11:09 ET) "
        "because the last pacer fired at 03:21 and none was armed after it.\n\n"
        "Note WHY it was dropped, because it will feel the same way now: arming lapsed while "
        "Brad was actively messaging, since his replies were doing the waking. The pacer felt "
        "redundant right up until it was the only thing left.\n\n"
        "ARM IT — its own call, run_in_background:true, no `&`, no `nohup`, not appended to "
        "another command (the sleeping process must BE the background task):\n"
        "    python ~/.claude/turn-pacer.py --label '<what happens next>'\n"
        "Omit --minutes so it adapts to how recently Brad spoke.\n\n"
        "If you are deliberately ENDING THE RUN (wind-down done, work finished, Brad said "
        "stop), say `pacer:none` and proceed. That use is logged."
    )
    _log("fire", "no pacer armed at turn end", transcript)
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

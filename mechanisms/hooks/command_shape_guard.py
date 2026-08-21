#!/usr/bin/env python3
"""Stop hook: this turn's own fenced shell block must not hand a Windows PowerShell operator a
command that will not run as pasted.

WHY THIS HOOK EXISTS
--------------------
The operator, three messages in about two minutes, 2026-08-15:

  "you've GOT TO STOP giving me powershell commands with the wrong slashes"
  "it wastes turns EVERY TIME"
  "EVERY powershell command I have to tell you to fix it"

A command in chat renders in a fenced block with a Run button in this harness -- so a
POSIX-shell idiom in that block is handed straight to him, and a wrong one costs a round trip:
he runs it, it fails or does the wrong thing, he reports it, a corrected one goes out. That is
strictly more expensive than the one turn this hook spends catching it before it ships.

MEASURED BEFORE BUILDING, per this estate's own rule (`docs/tool-enforcement-candidates.md`):
scanning this project's own transcript corpus (334 fenced code blocks, 291 in a shell-shaped
fence language) found the failure at 0.7% of shell-shaped blocks (2/291) -- both hits arguably
legitimate WSL/bash-context commands rather than the pattern the operator is naming, so the TRUE
rate on the pattern they mean is likely lower still. That is far below "every", which the third message
claims -- read as EITHER a very recent, unmeasured spike this corpus does not capture, OR (more
likely, given the aggregate rate) a small number of recent instances that felt like "every" in
the moment. Either way the fix is the same: catch it before it ships, cheaply.

WHY A `stop_gate.py` CHECKS ENTRY AND NOT A STANDALONE `Stop` HOOK
-------------------------------------------------------------------
`stop_gate.py`'s own docstring already made this argument once (duplicated blocking Stop hooks
cost the operator a re-read each): every check lives in ONE CHECKS list so all of a turn's objections
land in a single consolidated block instead of one block per check. A rare check (this one fires
on well under 1% of turns per the measurement above) costs nothing extra on the ~99% of turns
where it is silent, and on the rare turn it DOES fire, it joins whatever else that turn already
triggered rather than adding a second full round-trip. This is the cheaper shape the token-cost
argument for "a blocking Stop hook spends the exact resource it conserves" was pointing at --
CHECKS-list membership, not a freestanding settings.json Stop entry, is how that argument is
actually answered here. See the wiring note at the bottom of this file.

WHAT IT DOES
------------
On Stop, scan the fenced code blocks in THIS TURN's own assistant text (not tool results -- a
Bash-tool call the agent itself ran is unaffected by construction; only a fenced block the agent
is HANDING to the human counts) for the four defect classes in `command_shape_detect.py`. Fires
at most once per turn, honours `stop_hook_active`.

SCOPE GUARDS (each one is a false positive that would have discredited the hook)
  * Only fenced blocks in a shell-shaped fence language are scanned (see
    `command_shape_detect.SHELL_FENCE_LANGS`) -- a python/json/yaml/md block is not a command
    anyone can Run and scanning it would be pure noise.
  * A line that escapes into a POSIX shell (`wsl -e ...`, `docker exec ...`, `ssh ...`) is
    skipped whole-line -- its payload runs inside THAT shell, not PowerShell, and is correct as
    written.
  * `&&`/`||` are valid PowerShell 7+ and are never flagged.
  * A drive-letter path with forward slashes is skipped when every shell the block is written
    for is POSIX-only (inferred from the fence language being bash/sh/zsh/shell/console -- see
    `command_shape_detect`) -- there, forward slashes are the native, correct spelling.

OVERRIDE
--------
`command-shape:ok` anywhere in the turn proceeds. Logged both ways (fired-and-overridden,
would-not-have-fired-but-present) via `hook_log`, same decay-visibility discipline as
`evidence_with_claim.py` -- see that file's docstring for why both matter.

WIRING (not done by this hook or by an agent -- see conductor-bs/tools/note-find.py's own
convention: installing a hook is the operator's act)
------------------------------------------------------------------------------------------------
This file and `command_shape_detect.py` are copied to ~/.claude/hooks/ already (this IS that
directory). The only remaining step is adding this hook's filename to `stop_gate.py`'s CHECKS
list:

    "command_shape_guard.py",

anywhere in the list in ~/.claude/hooks/stop_gate.py (order only affects display order of a
combined block). `stop_gate.py` itself is already wired into Stop in settings.json, so no
settings.json edit is needed at all.
"""
from __future__ import annotations

import json
import os
import re
import sys

OVERRIDE = re.compile(r"command-shape:\s*ok\b", re.I)


def _import_local(name: str):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    return __import__(name)


def turn_said(transcript_path: str) -> str:
    """This turn's own assistant text, using the shared turn boundary (see turn_window.py's
    docstring for why a local reimplementation would be wrong the same way three prior hooks
    were). Fails open (empty string) on any import/parse problem."""
    try:
        tw = _import_local("turn_window")
        return tw.turn(transcript_path)["said"]
    except Exception:
        return ""


def _log(event: str, trigger: str, transcript: str, extra: dict) -> None:
    try:
        hl = _import_local("hook_log")
        hl.record("command_shape_guard", trigger=trigger, transcript_path=transcript,
                  extra=dict(extra, event=event))
    except Exception:
        pass


def evaluate(said: str) -> list[dict]:
    """Pure: violations found in this turn's fenced shell-shaped blocks. Empty means pass."""
    try:
        csd = _import_local("command_shape_detect")
    except Exception:
        return []
    return csd.find_violations_in_fenced_blocks(said)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed payload

    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    said = turn_said(transcript)
    violations = evaluate(said)
    overridden = bool(OVERRIDE.search(said))

    if overridden:
        _log("overridden" if violations else "preemptive",
             violations[0]["line"] if violations else "(no violation detected)",
             transcript, {"violations": len(violations)})
        return 0

    if not violations:
        return 0

    try:
        csd = _import_local("command_shape_detect")
        shown = csd.format_violations(violations[:6])
    except Exception:
        shown = "\n".join(str(v) for v in violations[:6])

    reason = (
        "This turn's own fenced command block will not run as pasted into PowerShell:\n\n"
        + shown + "\n\n"
        "The operator, 2026-08-15: \"you've GOT TO STOP giving me powershell commands with the wrong\n"
        "slashes\" / \"it wastes turns EVERY TIME\" / \"EVERY powershell command I have to tell\n"
        "you to fix it.\"\n\n"
        "FIX: rewrite the block using the replacement named above -- do not just restate the "
        "same command with a caveat.\n\n"
        "If this block is genuinely meant for a different shell (e.g. it is fenced/labelled for "
        "that shell, or every line in it is a `wsl -e ...` / `docker exec ...` escape into one), "
        "say so and emit `command-shape:ok`. Override use is LOGGED, including pre-emptive use."
    )
    _log("fire", violations[0]["line"], transcript, {"violations": len(violations)})
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

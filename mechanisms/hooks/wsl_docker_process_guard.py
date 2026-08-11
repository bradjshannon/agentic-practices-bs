#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell) guard: block hunting a Windows process for a WSL/Docker-backed port.

WHY THIS HOOK EXISTS
---------------------
2026-08-04: a conductor session needed to restart the iotta dev server on `:8000` to pick up a
code change, assumed it was a native Windows process, and burned several tool calls -- `tasklist`,
`wmic process where "ProcessId=X" get CommandLine`, PowerShell `Get-CimInstance Win32_Process
-Filter "ProcessId = X"` -- before finding nothing useful. `:8000` is not a Windows process at
all: it is served by a Docker container built from a SEPARATE WSL clone (`~/iotta-bs` inside WSL,
not the Windows checkout this agent was sitting in), documented as a "STANDING GOTCHA" in
`conductor-bs/conductors/iotta/decisions.md` and in `iotta-setup/RUNBOOK.md`'s "CI/CD -- the
deploy button" section. Both docs already said this in prose. The prose did not prevent the
mistake -- a session can start without ever reading either file, and a plausible-looking dead end
(no matching process) reads as "must search harder," not "wrong premise." That is the
Voluntary-class failure this repo's own doctrine predicts: a rule that only ever shapes what an
agent *writes* is satisfiable without the check ever happening.

WHAT IT DOES
------------
Blocks a command that hunts a Windows PID/process tied to the iotta dev/stable ports (8000, 8001)
or explicitly names iotta -- via `tasklist`, `wmic process`, `Get-CimInstance Win32_Process`,
`Get-Process` filtered by PID/name, or a `netstat` port lookup meant to feed a later `taskkill` --
and points at the actual restart mechanism instead:

    gh workflow run deploy.yml -f ref=<branch> -f target=dev     # dev = port 8000
    gh workflow run deploy.yml -f ref=<branch> -f target=stable  # stable = port 8001

SCOPE DISCIPLINE
-----------------
`tasklist` / `Get-Process` / `wmic process` / `netstat` are ordinary, frequently-legitimate
Windows admin commands for purposes that have nothing to do with iotta. Firing on them
unconditionally would cry wolf constantly and get the guard disabled, taking its true positive
with it. So this only fires when a process/PID-hunt shape co-occurs, IN THE SAME COMMAND, with a
signal that ties it to the iotta server: the literal port 8000 or 8001, or the word "iotta". A
`netstat -ano | findstr :8000` already carries that signal by itself -- it is the realistic first
step of the hunt, and blocking it there stops the chain before a PID even exists to feed the next
command.

Exit 2 blocks the call and shows stderr to the model. Exit 0 allows.
"""
import json
import re
import sys

# Same override convention as lying_command_guard.py: lives IN the command (auditable in the
# transcript), deliberate to type (not reachable by reflex).
OVERRIDE = re.compile(r"#\s*guard:\s*ok\b", re.I)

# Ports RUNBOOK.md documents as fixed/well-known: dev (:8000) and stable/prod (:8001). Named
# scratch instances (provision-instance.sh) get arbitrary ports chosen at creation time and can't
# be enumerated here -- those are covered by the "iotta" keyword instead, since a command hunting
# one is very likely to name the instance or the project somewhere in the same line.
_KNOWN_PORTS = ("8000", "8001")

# A command is "tied to iotta's WSL/Docker ports" if it mentions one of the known ports as a
# port-shaped token (not just any occurrence of the digits) or names iotta outright.
_PORT_RE = re.compile(r"(?<![\d.])(?:" + "|".join(_KNOWN_PORTS) + r")(?![\d])")
_IOTTA_RE = re.compile(r"\biotta\b", re.I)


def _has_context(text: str) -> bool:
    return bool(_PORT_RE.search(text) or _IOTTA_RE.search(text))


# ── THE TWO NARROWINGS ADDED 2026-08-09, after this guard blocked three unrelated commands ──
#
# It fired on a session doing conductor work that had nothing to do with the iotta server:
#
#   1. `grep -n "netstat\|8000\|8001..." wsl_docker_process_guard.py`  -- reading THIS FILE's own
#      source. The verbs and the ports were inside a grep PATTERN, i.e. data. This is the prose
#      trap lying_command_guard.py's rule 5 documents ("a guard that punishes writing about its
#      own patterns is one that gets disabled"), arriving here.
#   2. A multi-line block whose FIRST line set `SCRATCH=".../C--Users-<user>-Documents-GitHub-
#      iotta-bs/.../newuser"` and whose LATER line ran `netstat ... | grep :8917`. The context
#      signal came from a session scratchpad PATH on a different line -- `\biotta\b` matches
#      `iotta-bs` because `-` is a word boundary. In THIS project every scratch path contains
#      the project name, so that is a permanent false-positive source, not a one-off.
#   3. The same block's `taskkill` on port 8917, blocked for the same reason.
#
# Both narrowings are needed; each alone leaves one of the three firing.
#
# (a) SEGMENT the command on `;`, newline, `&&`, `||` -- but deliberately NOT on `|`. A pipeline
#     is one logical command, and `netstat -ano | findstr :8000` is this guard's canonical true
#     positive: splitting on `|` would put the verb and the port in different segments and the
#     guard would go silent on the exact incident it was built from. Context must now co-occur
#     with the verb in the SAME segment, which is what kills #2 and #3.
#
# (b) Look for the VERB in quote-stripped text, but for the CONTEXT in the raw segment. The
#     asymmetry is the point and is load-bearing in both directions:
#       * verb stripped  -> `grep -n "netstat..."` has no verb outside quotes, so #1 goes quiet.
#       * context raw    -> `findstr ":8000"` and `"CommandLine like '%iotta%'"` keep their
#                           signal, which lives INSIDE quotes in several real true positives.
#     A blanket shell_only() over both would have silently killed those.
# (c) STRIP HEREDOC BODIES FIRST. Found immediately after (a) and (b) shipped, by this guard
#     blocking the very `git commit` that carried its own fix: the message quoted
#     `netstat -ano | findstr :8000` while explaining why that case must keep working. A
#     heredoc body is prose being passed to a program, never commands the shell will run, and
#     backticked prose is not covered by _QUOTED (which only knows ' and "). Stripped before
#     segmenting, because a body spans the newlines the segmenter splits on. This is the fourth
#     instance of one root cause -- text ABOUT the guard read as an instance of the guard --
#     which is why lying_command_guard.py's shell_only() has done this from the start.
_HEREDOC = re.compile(r"<<-?\s*'?(\w+)'?.*?^\1\s*$", re.S | re.M)
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"", re.S)
_SEGMENT_SPLIT = re.compile(r";|\n|&&|\|\|")


def _segments(cmd: str):
    """Shell segments, splitting on `;`/newline/`&&`/`||` but never on a single `|`.

    Heredoc bodies are removed first: they are data handed to a program (a commit message, a
    file being written), not shell the guard should reason about.
    """
    return _SEGMENT_SPLIT.split(_HEREDOC.sub(" ", cmd))


# Windows process/PID-hunt shapes. Each is common enough on its own to be legitimate -- the
# `_has_context` gate above is what keeps this narrow.
_HUNT_PATTERNS = [
    ("tasklist", re.compile(r"\btasklist\b", re.I)),
    ("wmic process", re.compile(r"\bwmic\s+process\b", re.I)),
    ("Get-CimInstance Win32_Process", re.compile(r"Get-CimInstance\b[^|;\n]*Win32_Process", re.I)),
    ("Get-Process", re.compile(r"\bGet-Process\b", re.I)),
    ("netstat", re.compile(r"\bnetstat\b", re.I)),
    ("taskkill", re.compile(r"\btaskkill\b", re.I)),
]


def check(cmd: str):
    """Return a list of (problem, fix) for a command string. Empty list = allow."""
    if not cmd:
        return []

    # Verb outside quotes, context anywhere in the SAME segment. See the narrowings above.
    hit = None
    for segment in _segments(cmd):
        if not _has_context(segment):
            continue
        unquoted = _QUOTED.sub(" ", segment)
        for name, pattern in _HUNT_PATTERNS:
            if pattern.search(unquoted):
                hit = name
                break
        if hit is not None:
            break
    if hit is None:
        return []

    return [(
        f"This looks like it's hunting a Windows process/PID for iotta's dev (`:8000`) or "
        f"stable (`:8001`) port (matched `{hit}`). Those ports are not native Windows "
        f"processes -- they're served by Docker containers built from a SEPARATE WSL clone "
        f"(`~/iotta-bs` inside WSL, not this Windows checkout). A Windows-side process/PID "
        f"search will find nothing, and the empty result reads as 'search harder' instead of "
        f"'wrong premise.' See `conductor-bs/conductors/iotta/decisions.md`'s 2026-08-03 "
        f"\"STANDING GOTCHA\" entry and `iotta-setup/RUNBOOK.md`'s \"CI/CD -- the deploy "
        f"button\" section.",
        "To pick up a code change, deploy instead of restarting a process:\n"
        "      gh workflow run deploy.yml -f ref=<branch> -f target=dev     # dev = port 8000\n"
        "      gh workflow run deploy.yml -f ref=<branch> -f target=stable  # stable = port 8001\n"
        "      gh run watch                                                 # or: gh run view --log\n"
        "    To inspect the running container directly instead: "
        "`wsl -d Ubuntu-24.04 -- bash -lc \"cd ~/iotta-bs && docker compose ps\"` / "
        "`docker compose logs -f`.",
    )]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on a malformed payload

    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0
    if OVERRIDE.search(cmd):
        return 0  # explicitly overridden; the token is the audit record

    problems = check(cmd)
    if not problems:
        return 0

    try:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("wsl_docker_process_guard", trigger=(cmd or "")[:120])
    except Exception:
        pass
    print("Blocked: this command shape hunts a Windows process for a WSL/Docker-backed port.\n",
          file=sys.stderr)
    for problem, fix in problems:
        print(f"  - {problem}\n    FIX: {fix}\n", file=sys.stderr)
    print("OVERRIDE: append `# guard:ok` to the command to run it anyway.\n", file=sys.stderr)
    print("(~/.claude/hooks/wsl_docker_process_guard.py)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

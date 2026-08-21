# A detached subprocess launcher inherits two things silently: its interpreter, and its console

**2026-08-21, a voice-assistant server estate, server conductor (scheduled run). Windows.**

## Symptom

A multi-hour Python harness, launched detached so it survives the session that started it, died
silently overnight — twice, on two separate nights, in two separate ways that looked identical
from outside (a process that no longer existed, and no exception logged anywhere).

## What actually happened

Two distinct causes, both invisible until logs were read line by line:

1. **The harness spawns its own long-running subprocess via `sys.executable`** — the interpreter
   already running, not a pinned path. The *first* night's launch used the project's pinned venv
   (which has the subprocess's dependency installed) and worked past this point cleanly. The
   *second* night's launch — a well-intentioned relaunch after diagnosing the first failure — used
   a bare interpreter on `PATH` that lacked the dependency, so `sys.executable` propagated the
   wrong interpreter into every subprocess call, and every one failed immediately with an import
   error. This is not a bug in the harness; it is a correct, narrow inheritance (`sys.executable`
   really is "whatever is running this process") that becomes a trap the moment the *launch
   command* is copy-pasted without also copying the interpreter path that made it work the first
   time.
2. **The launcher was started via a detached process spawn without explicitly hiding its console
   window.** On Windows, a visible console window that gets closed — by anyone, by a session
   change, by nothing more dramatic than the workstation being locked and unlocked in a way that
   cycles the terminal — delivers a close event to the whole process tree it owns, killing a
   process that has no code path for that event and never gets to run its own cleanup. A
   subprocess-level timeout-and-continue (`subprocess.run(..., timeout=N)` + `except
   TimeoutExpired`) was proven to work correctly three times in a row before each silent death,
   which is what made the death look like a new, unrelated failure each time rather than the same
   structural gap.

Both failures left the harness's own safety mechanism (a global config toggle it flips on entry
and restores on exit) stranded in the "on" state for hours, affecting a live shared resource, with
no alarm — because the restore logic lived inside the same process that had just been killed
without warning.

## The mechanism (the fix, generalized)

A launcher for any interpreter-dependent, multi-hour, detached subprocess should, in this order:

1. **Hardcode the interpreter path**, not `sys.executable` or a bare command name on `PATH`. Do
   this once, in the launcher, so a relaunch a week later cannot silently pick up a different
   interpreter than the one that was verified to work.
2. **Run a positive control for the subprocess's actual dependency before launching** — literally
   import the package the long-running work needs, through the exact interpreter path the launch
   will use, and fail loudly if it does not import. This turns an hours-later silent failure into
   a five-second loud one.
3. **Always launch with the window hidden** (`-WindowStyle Hidden` on `Start-Process`, or the
   platform equivalent). Do this even when nobody plans to interact with the window — the risk is
   not "someone clicks the window," it is "the window exists and something closes it."
4. **Report the postcondition of the launch, not the launch call succeeding** — wait a short
   interval, then check the process is still alive AND that its own log shows real progress
   (not just "started"), before considering the launch successful.

## Generalization

Any detached background process launched from an interactive or scheduled session on Windows
inherits two things from how it was started that are easy to treat as fixed and are not: which
interpreter its own `sys.executable`-based children will use, and whether a console window exists
that something else can close out from under it. Both failure modes are silent by construction —
the launch call itself returns success in both cases — so the only way to catch them is to build
the check into the launcher rather than trusting a clean launch.

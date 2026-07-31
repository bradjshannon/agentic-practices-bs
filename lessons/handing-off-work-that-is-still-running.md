# Handing off work that is still running

## Symptom

A session ended with a long job "running in the background." The handoff said it would be finished
by morning. It had been dead for 45 minutes when the handoff was written, and the next session found
a log file frozen at the exact byte count it had reached when its parent session exited.

## What actually happened

Two independent failures, and either alone would have been enough:

**1. The job was session-scoped.** It was launched as a background job of the agent session. When
the session ended, the job was reaped. Nothing announced this — the log file remained on disk at
full size, with plausible content, ending mid-stream. **A stalled log and a working log are the same
bytes.** The only difference is an mtime nobody thought to check, because the handoff had already
asserted the answer.

**2. The output path was inside the session's own scratch worktree.** So even a *completed* run would
have been destroyed by routine cleanup. The job was arranged so that success and failure both ended
in nothing.

A third, smaller trap turned up while diagnosing it: the job's stderr was redirected to a file, so it
was **block-buffered**. Sampling the log to estimate progress reported a rate ~3× slower than
reality, which nearly produced a second wrong conclusion on top of the first.

## The rule

**"It's running in the background" is not a handoff. It is a claim with no verification path.**

For work intended to outlive the session:

- **Detach it from the session properly.** Use a mechanism whose lifetime is not the session's —
  a detached process (`Start-Process`, `nohup`, a service, a scheduled task), not a shell background
  job. Then *verify the parentage*: query the process table and confirm the PID exists and is not a
  child of the session.
- **Write output outside any ephemeral directory** — not a scratch dir, not a per-session worktree,
  not a temp path with a session id in it. Success must land somewhere that survives cleanup.
- **Hand off the CHECK, not the claim.** The handoff must contain: the PID or how to find it, the
  output path, the expected completion time, and *what a stalled run looks like*. "It will be done
  by morning" is unfalsifiable; "PID 39416, output at `<path>`, ~10 units/min, done ~23:20; if the
  `.err` mtime is older than a few minutes it is dead" is checkable in one command.
- **When inheriting such a claim, check before believing.** Compare mtime to now. The predecessor's
  confidence is not evidence; they wrote the handoff *before* the outcome existed.
- **Beware buffered progress signals.** Redirected stderr/stdout is block-buffered in most runtimes.
  If you are estimating a rate from a log, sample it twice over a real interval rather than dividing
  a single reading by elapsed time — and prefer a signal the job flushes deliberately.

## Why it generalises

This is the general shape of **inherited unverified state**, and background jobs are its purest
form: the claim is made at the moment of least information (before the work happened) and consumed
at the moment of least suspicion (by someone who was not there). Anything asynchronous has the same
structure — a queued deploy, a submitted batch job, a spawned agent, a scheduled task.

The deeper point is about *absence*: a job that dies silently and a job that is working quietly
produce identical observations. Whenever the failure mode and the success mode look the same from
the outside, the handoff must include the discriminator, because the next reader will not invent one.

Related: `verification-and-evidence.md`, `scheduling-and-autonomy.md`.

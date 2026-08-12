# A live session can outlive its own concurrency lease without dying

**Date:** 2026-08-12. **Cost:** a full sibling conductor cycle ran, unnoticed, inside one
session's own idle waits — benign this time by luck (different files touched), not by design.

## Symptom

A conductor session took a lease at the start of its run (`OK: lease acquired`), then did two
multi-hour passive waits — monitoring detached background processes via periodic polling and
scheduled wakeups, each individual gap well under an hour but the total waiting time far exceeding
the lease's 45-minute TTL. Nothing in the session ever explicitly renewed the lease during those
waits; it simply kept working normally between poll cycles, assuming the lease from step one still
covered it.

At wind-down, a status check on the lease returned `OK: no conductor lease held`. In the interim,
a separate scheduled trigger had fired, found the lease free, run an entire independent
prime-work-winddown cycle of its own, and released it again — all while the first session was
still alive, still being actively steered by a human, and about to dispatch three more subagents
and push several more commits.

## What actually happened

The lease was designed correctly for the failure mode its own documentation names: *"an agent has
no stable OS process, so a dead run's lease expires by itself and the only cost is a skipped cron
tick, which costs nothing."* That reasoning is sound for a session that crashes, gets killed, or
is abandoned — anything where "the lease expired" and "the session is gone" are the same event.

It is not sound for a session that is genuinely alive but *quiet* for longer than the TTL. A
conductor that launches a long detached job and then polls it periodically is, from the lease's
perspective, indistinguishable from a dead one — nothing in the polling loop touches the lease at
all, because the lease was designed around "is the process still running," and a session waiting on
background work is not doing anything the lease mechanism was built to notice.

The gap is structural, not a one-off oversight: **any session whose real wall-clock duration
exceeds the TTL, for any reason — a long build, a slow eval, a subagent that takes twenty
minutes — will silently lose lease coverage partway through**, even though nothing about the
session actually failed.

## The rule

**A liveness lease needs a heartbeat wired into every wait primitive the session actually uses,
not just into its own event loop.** If a session's control flow includes polling loops, scheduled
wakeups, or background-task waits that can individually or cumulatively exceed the TTL, each of
those wait points needs to renew the lease on the way through — the same way a long-running web
request renews a session cookie, not just the login action that first created it.

Absent that: either (a) set the TTL to comfortably exceed the longest wait pattern a session of
this kind is expected to make, accepting that a truly-dead session takes longer to be noticed, or
(b) treat "lease expired" as advisory rather than authoritative once a session has confirmed a
sibling's last real activity postdates the TTL by a wide enough margin — which is exactly the
workaround the sibling session in this incident had to invent for itself, because the lease alone
could not tell it whether the holder was dead or merely quiet.

## Why it generalises

This is the same shape as any liveness check built on "did the thing check in recently": a k8s
pod's readiness probe during a legitimate long GC pause, a distributed lock with too short a lease
next to the critical section it protects, a heartbeat monitor watching a process that's doing real
work synchronously and can't poll back. **The lease is measuring "is anyone renewing this," not
"is the underlying work still happening"** — and any workload with a wait longer than the renewal
interval will read as dead while it is very much alive.

The fix is never to lengthen the TTL indefinitely (that just slows detection of the failure mode
the lease actually exists to catch); it's to make renewal a property of *waiting*, not just of
*acting* — every point where a session blocks or polls is a point that should touch the heartbeat,
because from the outside, waiting and dying look identical until something says otherwise.

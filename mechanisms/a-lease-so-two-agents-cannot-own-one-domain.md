# A lease, so two scheduled agents cannot own one domain

**Enforcement class: structural-but-cooperative.** It cannot stop an agent that never runs the
launcher. It *does* remove the case that actually happened — two agents each believing, on
evidence, that they were alone.

Built 2026-07-31 after a scheduled agent ran a shared estate for a morning beside a sibling and
neither detected the other. Full account: `lessons/commit-authorship-is-not-evidence-a-human-acted.md`.

## What it replaces

A check that asked *"is a collaboration-log row open?"* — true only while an agent is **mid-write**.
A sibling that is reading, thinking, or between actions is invisible, so a clean preflight reads as
proof of solitude. The instrument could not have said "someone is here" for most of a run.

## Where it lives

| File | Role |
|---|---|
| `conductor-bs/tools/conductor-lease.py` | The lease. `acquire` / `renew` / `release` / `status`, `--domain <name>` |
| `conductor-bs/tools/test_conductor_lease.py` | 15 tests, mutation-verified |
| `conductor-bs/tools/conductor-identity.py` | Names the commit author so `%an` stops meaning "a human" |
| `conductor-bs/tools/test_conductor_identity.py` | 9 tests, incl. that the human's own commits stay theirs |
| `ai-research-bs/scripts/conductor/Start-ServerConductor.ps1` | Calls both at preflight |

## The design decisions that are load-bearing

- **Taken, not inferred.** Occupancy is the default state of a running agent, not a side effect of
  its current activity.
- **Heartbeat expiry, not a PID.** An agent has no stable OS process — the shell dies between tool
  calls. A crashed run's lease expires by itself; the cost is one skipped scheduled tick.
- **Local file, not a repo file.** Co-located agents; a repo file needs a push to be visible and
  races on the boundary it protects.
- **Normalise the holder id.** A launcher passes `D:\path`, a hand-run passes `D:/path`. Compared
  raw, an agent fails to renew *its own* lease, then reads **itself** as a live sibling.
- **Refuse to release someone else's.** Otherwise "cleanup" creates the concurrency.
- **Acquire on the *preflight* path.** The scheduled flow is "preflight, then work", so a lease
  taken only on the other path is inert exactly when needed. A `-NoLease` switch covers a human peek.
- **Exit codes are the contract** (`0` yours/free, `3` a live sibling) so the launcher branches on a
  value, not on parsed prose.

## What it cannot detect

- An agent that **does not run the launcher** — started by hand, or from a different entry point.
- An agent on a **different machine** (the lease is a local file). Co-location is an assumption,
  and it is the current truth, not a guarantee.
- A **stale-but-alive** holder: an agent that runs longer than the TTL without renewing looks dead
  and can be displaced. Renew on a heartbeat if a run may exceed it.
- Anything about **what** the sibling is doing. It answers "is someone here", not "are we
  colliding".

## The identity half, and its asymmetry

`conductor-identity.py` sets a per-**worktree** `user.name` (`<Role> (<worktree>)`) and deliberately
leaves `user.email` alone, because forges link commits to accounts by email and `%an` is the field
that gets printed.

**It only generalises where the agent is isolated.** An agent that shares a clone with its human —
as a sibling agent in this same setup does — would have its persistent `user.name` relabel *the
human's own* commits. That is worse than the problem. The convention ("an agent names its commits")
generalises; the mechanism does not, until the agent has its own worktree. The test that encodes
this is `test_the_shared_clone_still_commits_as_the_human`.

## Verify it by breaking it

Both suites were checked by mutation, not by passing:

- remove the holder normalisation → only the path tests fail
- make the "sibling holds it" branch unreachable → refusals fail across three classes
- degrade `--worktree` to repo-wide → the human's-commits-stay-theirs test fails

If a guard's tests still pass after you break the guard, they were assertions.

# The harness caps ONE live instance per named agent type per session

**Date:** 2026-08-27. **Cost:** several failed `Agent` dispatches mid-wave, each requiring a
diagnosis-and-retry before the fan-out could continue.

## Symptom

Mid-wave, with several named agent types (`iotta-server`, `iotta-sdk`, `iotta-firmware`, …) already
dispatched and running, a fresh `Agent` call using a type that already had a live instance failed
outright:

```
You already have a 'iotta-server' agent this session. Reuse it like an SME rather than
paying to prime a new one.
  agentId     a729ecf17f59c5d12
  ...
REPLACEMENT — resume it with its context intact:
  SendMessage(to: 'a729ecf17f59c5d12', ...)
```

This fired even when the two tasks were completely unrelated (different lots, different files,
different repos) and even when the existing instance was still busy on its own task. It also fired
again *after* that instance had finished and returned its result — the guard did not appear to
distinguish "busy" from "recently existed."

## What actually happened

The conductor's mental model was: agent *type* names a role (an SME with a fixed toolset and
system prompt), and any number of instances of that role can run concurrently, the same way you'd
spin up five generic workers. That model is wrong for this harness. **A named agent type is capped
at one live instance per session** — dispatching a second one is not "starting a parallel worker,"
it is an error condition the harness actively prevents, with the prescribed remedy being to
`SendMessage` the existing instance a new task once it becomes free.

The two things being conflated:
- **Agent type** (`iotta-server`, `iotta-sdk`, …) — a role definition: system prompt + toolset.
- **Agent instance** — a single running (or completed-but-resumable) conversation with that role.

The type is not a stamp you can print as many copies of as you want; it is closer to a named,
singleton worker that you queue tasks to sequentially via `SendMessage`, and only ever have one
fresh copy of at a time per session.

## The rule

**Before dispatching an `Agent` call with a named type, check whether that type already has a live
or recently-completed instance this session.** If it does, `SendMessage` it the new task instead of
calling `Agent` again — this is not a fallback for when the direct call fails, it is the correct
default. Only call `Agent` fresh for a type that has never been dispatched this session, or when
you deliberately want a COLD agent (an adversarial verify, where a revived agent is contaminated by
its own prior conclusion — that is a correctness reason, not a cost one, and the harness's own
cost-guard message says as much when it lets a second instance through).

**Practical consequence for wave planning:** if a wave's lot count exceeds the number of *distinct*
agent types you're willing to use, some lots will serialize through `SendMessage` on a shared type
rather than truly running in parallel. Size a wave's expected concurrency around distinct types
available (`iotta-server`, `iotta-sdk`, `iotta-firmware`, `iotta-scout`, `general-purpose`,
`claude`, …), not around lot count — two lots of the same "flavor" queued on one type is not two
concurrent lots.

## Why it generalises

Any harness or framework that offers "named roles" as its dispatch unit is a candidate for this
same confusion: the name looks like a class you can instantiate freely, but the runtime may treat
it as a singleton slot with a resume-don't-recreate discipline. The tell is a rejection message
that offers a *specific existing instance* to resume rather than a generic "try again" — that shape
of error is the harness telling you the abstraction is singleton-per-name, not class-per-name.

# A mechanism classified "Structural" delivered 6.2% of the time, because it sat below an early return — 2026-08-10

## Symptom

A SessionStart hook injects two things into an agent's turn-0 context: any **pending operator input**, and a **standing-guidance index** — the manifest of files every run is required to read. The second is the load-bearing one. A whole documentation discipline rested on it: "put the pointer in the manifest and the next agent gets it," and that pointer was treated as **Structural** on the enforcement ladder — works on an agent that never read the rule, because a hook delivers it with no agent participation.

Measured across the hook's entire lifetime: it reached **57 of 923 sessions — 6.2%**.

## Cause

```python
def main() -> int:
    inbox, inote = unhandled_inbox()
    sections, snote = instruction_sections()
    stale, stnote = stale_cards()

    if not inbox and not sections and not inote and not snote and not stale and not stnote:
        return 0  # genuinely nothing pending -- stay quiet

    ...print the pending-input block...
    ...print the standing-guidance index...   # <-- 50 lines below the return
```

The early return is correct **for what its comment says it is doing**: with no pending input, say nothing about pending input. But the guidance index had been appended to the same function later, underneath it. So a block whose entire value is unconditional delivery became conditional on *whether the operator happened to have unread messages* — two things with no relationship at all.

Nothing announced it. The hook exits 0 either way. On a busy day it fires and looks perfect; on a quiet day it emits zero bytes, which is indistinguishable from "the hook isn't installed" and from "there was nothing to say."

## Why nobody caught it for weeks

The failure is **anti-correlated with the moment you would notice**. You inspect a hook when you are actively working the queue — which is exactly when the inbox is non-empty and the guidance prints. The sessions that lost it are the quiet ones, where no one was watching, and where a cold agent starting from nothing needed the manifest most.

It also survived review because reading the code top-down, the early return is obviously right and the guidance block is 50 lines away. The bug is not in either piece; it is in their *adjacency*, which no local reading surfaces.

## The rule

**A mechanism's enforcement class is a claim about its delivery, and delivery is measurable. Measure it.** "It is Structural" is a design intention until you have a number: how many of the last N runs actually received it? If you cannot produce that number, the honest class is Unknown, not Structural — and Unknown should worry you more than Voluntary, because Voluntary at least expects decay.

Two concrete practices:

- **Never append an unconditional output below a conditional return.** If a function has an early exit for one concern, a second concern added later must not live downstream of it. Extract it to its own function and call it on every path — which also makes the unconditionality visible at the call sites instead of implied by line order.
- **Instrument delivery, not just execution.** Exit 0 says the hook ran. It says nothing about whether it emitted the thing it exists to emit. Where it matters, count the sessions that received the payload and check that number against the sessions that started.

## Why it generalises

Every agent system accumulates "this is handled by a mechanism" beliefs, and those beliefs are what let a team stop checking. The dangerous ones are not the mechanisms known to be flaky — those get watched. They are the ones with a *correct* implementation of a *different* scope than the one people rely on, failing silently in the half of the state space nobody is present for. The tell is always the same shape: a green exit code standing in for a capability, with no observation of the capability itself.

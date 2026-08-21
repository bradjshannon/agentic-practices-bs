# A guard built for the automatic path also vetoes the human one

*2026-08-12, a device-firmware project — merged, then noticed within the hour by an unrelated lot.*

## Symptom

A destructive-operation guard shipped to fix a real data-loss bug. It worked. Hours later a
different lot, on a different board, reported that it could not recover a corrupted disk — the
recovery tool refused. The refusal was correct by the guard's own logic and had never been
decided by anyone.

## What actually happened

The original defect was **automatic**: under memory pressure a failed allocation could launder a
"read failed" error code into a "no filesystem here" one inside a third-party filesystem library,
so firmware would reformat a perfectly healthy card that nobody had asked it to touch.

The fix was right, and structural rather than a race-narrowing patch: decide from a direct sector
read into a statically-allocated buffer the firmware already owns, and erase only if those reads
*succeeded* and genuinely showed no filesystem. A failed read became a refusal.

But that check was wired in as an unconditional final gate at **every** call site — including the
one reached by an operator explicitly sending `{"confirm": "ERASE"}`. And the "filesystem found"
verdict fires on any recognizable filesystem, **including a corrupt one the OS itself cannot
mount**. So:

- the automatic path was fixed (the goal), and
- the manual recovery path was silently removed (never discussed, never in a commit message,
  not in the review).

The second board's card was corrupt and unmountable. The on-device tool that exists precisely to
reformat such a card now refused it, because a corrupt filesystem is still *a filesystem*. The
capability loss was invisible until something needed it.

## The rule

**When you guard a destructive operation, enumerate its callers and decide each one separately.
"Automatic" and "a human explicitly asked" are different authorities and usually deserve
different answers.**

Concretely, before merging a guard on a destructive path:

- List every call site the guard now sits on. If they do not all share the same *authority*, the
  guard needs a parameter, not a single unconditional check.
- Ask what the guard's verdict means at its edges. Here, "a filesystem is present" was doing
  double duty: it meant *this disk has data worth protecting* on the automatic path, and
  *therefore you may not repair it* on the manual one.
- Ask directly: **does this remove a capability someone relies on?** A guard that only ever
  refuses looks identical to a working one until the day it should have said yes — and a
  refuse-only guard passes every test written for the bug it fixed.

## Why it generalises

This is not about disks. The shape is: *a fix aimed at an unattended code path gets installed at
a choke point shared with an attended one.* It recurs anywhere a safety check sits below the
level at which intent is known — rate limiters that also throttle the operator's manual retry,
confirmation prompts suppressed for automation that then suppress the human's, idempotency keys
that reject a deliberate replay, "are you sure" gates that a script bypasses and a person cannot.

Two properties make it hard to catch and are worth naming:

1. **The failure direction is the safe one**, so review waves it through. Refusing to destroy data
   is exactly what you asked for, and nobody argues with a guard that is too careful.
2. **It has no symptom until someone needs the capability.** The bug is an absence. Nothing logs
   "a thing you can no longer do", and the tests written alongside the fix all assert refusal —
   they are, structurally, unable to notice.

The cheapest defence is the enumeration above, done *before* the merge, because after the merge
the guard is load-bearing and removing it looks like reintroducing the original bug.

Related: [a-fix-hardens-the-path-the-findings-named-and-leaves-the-one-that-fires](a-fix-hardens-the-path-the-findings-named-and-leaves-the-one-that-fires.md)
is this lesson's mirror image — there the fix missed a path it should have covered; here it
covered one it should not have.

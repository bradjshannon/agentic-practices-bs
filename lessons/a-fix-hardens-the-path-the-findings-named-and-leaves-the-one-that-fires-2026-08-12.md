# A fix hardens the path the findings named, and leaves the one that actually fires

**2026-08-12.** Three rounds of adversarial review on one diff — an SD-card erase gate. Each round
found real blocking defects the previous round missed. The diff had *already* passed one review and
a hardware session before round one.

| round | what it found |
|---|---|
| 1 | the decision table erased a healthy card that was merely too full for the write probe |
| 2 | `errno` was discarded, the free-space guard had zero cluster headroom, and the erase ran against a second mount whose card identity was never compared |
| 3 | **all of round 2's hardening went onto a branch the real card never takes**, and the identity comparison it added is dead code |

Round 3 is the lesson.

## The shape

Review findings are written about the code path the reviewer happened to trace. A conscientious
author then fixes *exactly those*. The result is a diff where the named path is genuinely, carefully
hardened — probe, re-mount, re-derive the decision, compare identity — and the **sibling path that
reaches the same destructive call gets nothing**, because no finding pointed at it.

Here the hardened path was "mount succeeded but the write probe failed." The unhardened path was
"mount failed" — which went straight to the erase from a single read. The card on the bench took the
unhardened path **12 times out of 12**. Every improvement in the diff was on the branch it never
touched.

Nobody was careless. The author confirmed each finding by reading the code, corrected the reviewer
on one point by reading the vendor's source, and reported honestly what they could not observe. The
gap was structural: **a findings list is a sample, and a fix scoped to the sample inherits the
sample's blind spot.**

## The general form

> **When you fix review findings, enumerate every caller of the dangerous operation and state what
> protects each one. Do not fix the paths in the findings list.**

The findings tell you the operation is dangerous. They do not tell you where else it is reached
from. Answering "which paths reach this call, and what guards each" is a different question from
"are these five findings addressed", and only the first one closes the class.

The tell is a diff that adds a helper and calls it from one place, when the thing it protects is
called from two.

## The second half: the guard that cannot fire

Round 2 asked for a card-identity comparison across the two mounts. Round 3 found it present,
reachable, and **inert**:

```c
card = NULL;
board_sd_mount(/*format=*/false, &card);      // vendor writes *out_card ONLY on success
...
bool identity_confirmed = true;                // <- default
if (decision == ERASE && card != NULL) {       // <- never true on the failure path
    identity_confirmed = cid_matches(...);
}
if (decision == ERASE && identity_confirmed) { /* erase */ }
```

On the branch that mattered the handle was guaranteed NULL, so the comparison never ran and its
default let the erase through. The commit message stated the comparison happened. A config comment
claimed a debug build *proved* the sequence — proving a branch that never executes.

> **A guard whose default is "proceed" is not a guard; it is a comment with syntax.** When the
> evidence for a safety check cannot be read, the answer is REFUSE, never the initialiser you
> happened to pick.

Two independent checks would have caught it in seconds: does the value the guard reads ever get
written on this path, and does the guard's failure mode point at the safe outcome?

## What to actually do

- **For any destructive or irreversible operation, list its callers before reviewing the fix.** That
  list, not the findings, is the acceptance criterion.
- **Make the fix's own claims falsifiable.** "Compares identity across both mounts" is checkable in
  one grep of where the handle is assigned. A claim in a commit message costs nothing to write and
  is believed by everyone downstream.
- **Budget more than one adversarial round when the operation destroys data.** Rounds 2 and 3 each
  cost a fraction of what one wrongly-erased card costs, and each found blocking defects. The base
  rate of surviving defects after one review was, measured here, not close to zero.
- **A reviewer being wrong about a mechanism does not make the concern wrong.** Round 2 misdescribed
  *how* the erase fired; the erase risk was real, on a path round 2 never named. Re-derive the
  mechanism, keep the worry.

Related: `guard-the-selection-not-just-the-reading.md`,
`a-check-that-cannot-fail-reports-holds-forever-2026-08-01.md`,
`a-recovery-check-placed-after-the-failure-it-recovers-from-never-runs-2026-08-12.md`.

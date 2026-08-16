# "Fixed at the one site" is a claim about the call graph — 2026-08-16

## Symptom

A defect was fixed two days earlier, deliberately and well: rather than translating ~16 scattered
error strings, the fix intercepted them at the single point where a tool result reaches the
speech synthesizer. The commit message argued the reasoning explicitly and correctly — *these are
a CLASS, not a list; the seventeenth error path would otherwise reach a user the same way.*

The defect was still live. Probing the feature by hand reproduced it in one command.

## What actually happened

There were **two** chokepoints, not one.

The fixed one was on the normal request path. The unfixed one was on a **fast path** — a
deterministic pre-LLM interception that resolves an utterance and returns early, never reaching
the function the fix guarded. Every deterministic shortcut in the system (exit command, wake word,
keyword match, cached dispatch) resolved through that second site.

So the fix was correct, the reasoning behind it was correct, and the *count* was wrong. Nobody had
enumerated the callers. The class-vs-list argument is a good argument about **what** to fix; it
says nothing about **how many places** the thing being fixed occurs, and the commit slid from one
to the other without noticing.

The fast path is also, structurally, the one you are least likely to test by hand: it is the
optimised route for the commonest commands, so it is fast, quiet, and produces correct-looking
behaviour in every respect except the one that broke.

## The rule

**When a fix claims to close a class "at the chokepoint", verify the chokepoint is singular before
believing it. Enumerate the callers; do not infer the count from the quality of the argument.**

Concretely, before accepting "fixed once, at the one site":

- Grep for every caller of the guarded function, and every path that *returns before* reaching it.
- Ask specifically: **is there a fast path?** A cache hit, an early return, a deterministic
  matcher, a precomputed response. Those bypass the slow path's guards by design — that is what
  makes them fast.
- Exercise the feature on the fast path, not just the general one. Pick an input that is
  deterministic and changes no state, so the probe is repeatable and safe.
- Prefer a discriminator in the output that tells you **which path ran**. In the case above the
  record carried a `channel` field: one value meant the slow path, another meant the fast path. The
  first verification attempt passed while exercising only the slow path, and would have read
  identically against the unfixed code.

That last point generalises past this rule: **a test that cannot tell you which code path it
exercised has not verified the path you care about.**

## Why it generalises

This is not about error strings, or speech, or any one stack. It is about a reasoning move that
looks like rigor and is not:

> A well-argued claim about the *nature* of a defect gets its confidence transferred to an
> unexamined claim about the *extent* of it.

The better the argument for the fix's shape, the less anyone re-checks its scope — the commit
reads as thorough, so the site count reads as verified too. Reviewers see careful reasoning and
approve; the next reader inherits "this class is closed" as settled fact.

Two amplifiers make it worse:

1. **Fix-at-the-chokepoint is usually the right instinct**, so the pattern recurs constantly and is
   worth defending — the rule here is not "don't do that", it is "count the chokepoints".
2. **Monitors do not catch it.** The occurrence monitor for this defect class showed an
   unchanged count across the entire window the second site was live — correctly, because it only
   counted real user traffic and there was almost none in that window. A flat count on a quiet
   population is not evidence of absence, and it reads exactly like a fix holding.

## Related

- `mechanisms/` — anything asserting a guard is "the single site" should name how the count was
  established, not just why the site was chosen.
- The companion reading error: pairing a flat occurrence count with the window's actual traffic
  volume before concluding anything from it.

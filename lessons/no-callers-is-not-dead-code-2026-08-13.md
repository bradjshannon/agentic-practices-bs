# "Zero call sites" is not "dead code" — the deciding evidence may be a comment

**2026-08-13.** An over-engineering audit produced its cleanest deletion candidate: a ~672-line
FFT module, fully tested, with **zero call sites across every repo in the project**. Delete from
build. Nothing about the measurement was wrong.

The lot sent to execute the deletion refused it.

## What the grep could not see

The consumer was not a caller. It was a comment in a *different repo*, in live shipping code,
recording that its author had already evaluated this exact function for this exact feature and
rejected it **for a quantified hardware reason** — a 256-point spectrum allocates ~4 KB of heap,
and the target board had been measured as low as 1.4 KB of free internal DRAM. The comment named
the module by filename as the reactivation path if the memory budget ever loosened.

So the true state was not "nobody ever used this." It was:

> evaluated once, rejected on a measured constraint, with the primitive's continued existence
> named as the contingency plan.

Deleting it would have falsified a documented decision *and* destroyed a validated implementation
that whoever revisits that constraint would have to derive again from scratch.

## Why this is a general trap and not a lucky catch

A call-site census measures **current invocation**. Three states produce zero call sites and only
one of them is dead code:

| state | zero call sites? | delete? |
|---|---|---|
| nobody ever needed it | yes | yes |
| it was needed, tried, and rejected on a constraint that may lift | yes | **no** |
| it is invoked through a path the search cannot see (build config, reflection, generated code) | yes | **no** |

The census cannot distinguish them, and its output *reads* like a verdict. That is what makes it
dangerous rather than merely incomplete: an audit that reports "zero callers" hands the executing
agent a number that feels like it settles the question.

## The rule

**Before deleting on a zero-caller finding, search for the decision, not just the call.** Grep the
symbol's *name* across prose — comments, ADRs, design docs, changelogs — in every repo, not only
for invocations. A rejected-for-a-reason module is usually documented at the site that rejected it,
which is exactly the place a call-site search does not look.

And put the escape clause in the brief: *"if you find a consumer, STOP and report it; do not
delete."* That sentence is what fired here. The executing lot had every reason to trust the audit
and did the search anyway because it had been told what to do if the premise failed.

## The corollary for the person who declines

Say how anyone would know you were wrong. This lot did: if the comment were stale prose nobody
would act on, the tell would be a superseding correction beside it or a diverged reimplementation
elsewhere. It checked for both, found neither, and reported that check as part of the refusal.
A refusal without its own falsifier is just a different unverified claim.

Related: `a-subagents-negative-is-not-evidence.md`, `a-spec-is-not-ground-truth.md`,
`absent-from-where-i-looked-is-not-absent-2026-08-01.md`.

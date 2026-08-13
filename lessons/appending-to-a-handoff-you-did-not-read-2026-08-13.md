# Appending to a handoff you did not read — twice in one run (2026-08-13)

**The failure:** a conductor wrote into the handoff file *directly above* a passage that answered
the thing it was writing. Twice in the same run, in two unrelated domains. Both times the correcting
text was already on disk, already dated, already in the priming list.

## Instance 1 — a dispatched lot that re-derived a finished pass

The card board's sweep verdict read *"54 of 94 open cards (57%) were not measured at all… mostly not
looked at"*. The conductor dispatched a lot to triage the 51 checkless cards.

**The previous run had already run that exact pass**, and its result was one entry down in
`decisions.md`: 9 PROPOSE / 9 NOT-EXPRESSIBLE / 43 SHOULD-STAY-UNCHECKED. The new lot independently
reached 2 PROPOSE and 49 reasoned refusals — the same conclusion, at full cost.

## Instance 2 — repeating a correction the file itself contained

Measuring disk pressure, the conductor wrote that 42 worktree directories were *disposable* because
their branches were ancestors of `main`. The tool's own verdict was **KEEP 46 / SAFE-PRUNE 4 /
REVIEW 1** — its SAFE-PRUNE means *dead directory **and** merged branch*, and it has no mode that
removes a live worktree, deliberately.

A conductor had recorded that exact distinction in that same file the day before: *"ancestor-of-main
is not the same predicate as safe-to-delete, and I should not have written the stronger claim."* The
correction was ~150 lines below where the new wrong claim was inserted.

## Why it happens, and why "read the handoff" does not fix it

The handoff is **long, and it is the file you are about to edit**. Opening it to append feels like
having consulted it. Two structural pressures make skipping it rational in the moment:

- **The priming manifest hedges.** It lists the handoff among many files and says *"read the ones
  relevant to what you are about to do."* At prime you do not yet know what you are about to do, so
  nothing reads as relevant, and the hedge licenses the skip.
- **A queue instrument creates urgency the handoff would defuse.** In instance 1 a sweep verdict
  said the board was neglected; the handoff said it had just been audited. The instrument was
  louder, more recent-feeling, and wrong. **Whichever surface is noisier wins, and it is not the one
  with the answer.**

## What to do

- **Before dispatching a lot, grep the handoff for its subject.** Not "read the handoff" — a
  targeted grep against the specific thing you are about to spend on. One command, and it is the
  same discipline as `git log -- <the file the fix would touch>` before writing a brief.
- **Treat a queue instrument's alarm as a claim about the past**, exactly like a card. Instance 1's
  verdict was arithmetically correct and its *framing* was wrong: it summed 48 deliberately-
  uncheckable cards with 6 budget-starved ones into "not measured at all". A number that conflates
  populations manufactures work.
- **Before writing a stronger claim than your tool supports, run the tool.** In instance 2 the
  predicate ("merged") and the decision ("safe to delete") differed, and the tool encoded the
  difference. Asserting past your instrument is how a wrong claim gets an instrument's authority.

## The mechanism candidate, NOT built

Prose failed here twice in one run, so by the enforcement doctrine it should move up a class. The
cheapest structural version: have the session-start hook **print the current START-HERE block and
the newest handoff entry's headings inline**, rather than listing the file among many and hedging on
relevance. That removes the "is this relevant yet?" judgement entirely — the answer is in the
context window before the first decision is made.

**Deliberately not built here**, and the reason matters: it was identified at 46% context with a 50%
wind-down gun, and a session-start hook affects every future run. A guard built badly in the tail of
a window is worse than one built deliberately at the head of the next. Named so the next run can
decide, not so it inherits a half-mechanism.

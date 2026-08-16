# An anecdote tracks failure history, not effectiveness

**2026-08-15.** A run contract had grown to 2,073 lines, much of it dated incidents attached to
rules — the measurement, the operator's verbatim words, what the failure cost. The working belief,
written into the document itself in several places, was that this prose is load-bearing: cut the
story and the rule decays.

The operator asked the question nobody had: **how load-bearing is a dated incident?**

## The measurement

The document records its own repeat violations inline — `SECOND INSTANCE`, `THIRD INSTANCE`,
*"failed four times as a prose rule"*, *"by a conductor that had READ this rule earlier in the same
run"*. Those markers are a dataset: each one is an observation of a rule failing **while its
anecdote was present, and in some cases had just been read**.

Cross-tabulating every rule carrying a repeat marker against its anecdote length and its
enforcement class:

- **Every rule with a documented repeat was still voluntary at the time of each repeat**, anecdote
  already written and in place. One kill happened ~90 minutes after the lesson about the previous
  kill was written and committed.
- **Repeats stopped only where a guard was built afterward** — 5 of 10 sampled rules.
- **The rule with the longest anecdote had the worst trend**: ~30 lines and two full retellings, a
  third instance its own text calls "the worst of the three", and deliberately unmechanized.

The document's own stated remedy for a repeat is always *"a rule that fails twice moves up a class,
not another rewrite."* If anecdotes worked, the remedy for a repeat would be a better story. It
never is.

## The limit, which matters

This **cannot** distinguish *"the anecdote failed"* from *"the anecdote held down an even higher
rate"*. The document records failures only: a follow-up paragraph gets written when a rule breaks
again, never when it quietly holds. There is no long, purely-voluntary anecdote with zero recorded
repeats to serve as a positive control for anecdotes working on their own.

What **is** settled: in every recorded repeat, the anecdote alone did not stop it, and the fix that
did was always mechanical.

## Why the causation runs the way it does

An anecdote gets written **when a rule fails**. So length accumulates with failure history. The
most-anecdoted rules are the ones that have failed most — which reads from the inside like "this
rule is well-supported" and actually means "this rule keeps breaking and nobody has mechanized it."

## What to do with it

- **Do not treat anecdote mass as evidence a rule is working.** Read a long dated incident as a
  *failure count*, and ask why the rule has not moved up a class.
- **Do not prune anecdotes to save space either** — measured on the same document, the case
  evidence for still-voluntary rules was ~15% of the file, and cutting it buys little while
  removing the only argument a reader has for following the rule at all.
- **The move is to mechanize the rule and then drop its story**, in that order. Case evidence for a
  rule a machine now enforces is genuinely free to cut: a machine does not decay.

## A trap in measuring this

Judging "how much of this file is anecdote" by eye is unreliable in a **knowable direction**. An
informal read of the front matter — the densest section — produced ~65% anecdote; a seeded random
sample over the whole file measured ~21%. A **3x overestimate**, caught only because the
classification was checked against hand labels rather than extrapolated from the busiest part.

And when counting which anecdotes are "already mechanized", **verify each named mechanism is
actually built and wired**. The same document names several mechanisms that were proposed,
measured at a high false-positive rate, and correctly dropped. Counting those as built is the one
error that returns a dangerously large prunable number.

# A claim about your own state is a measurement, not introspection

## Symptom

Mid-task, the agent wrote: *"I'm at 73% context — once they land I'll write the handoff rather
than start the S1 change on a thin margin."* It then began sequencing work around that number:
deferring a live server change, teeing up a wind-down.

The operator replied: *"you are at 48% context."* The real figure was **47.9%** — a 25-point
error, in the direction that manufactured urgency.

## What actually happened

The number was never read. It was produced the way a person estimates how tired they are.

Two independent guards should have caught it and neither did:

1. **The agent's own contract said not to do this.** Its brief carries an explicit rule —
   never act on an estimated context number, read it from the transcript with a specific
   tool — written after a *previous* run wound down at an estimated 70% while actually at 32%.
   The rule was known, had a worked precedent attached, and still did not fire.
2. **A turn-end evidence hook was active** and did not object. It matches verification
   vocabulary ("verified", "confirmed") and negative-existence claims ("there is no X").
   `I'm at 73%` is a bare first-person assertion and matches neither.

The common cause: **a self-report does not feel like a claim.** Claims about the world get
checked because they are obviously about the world. Claims about the self bypass checking
because they present as introspection — direct access, nothing to look up.

For an agent that inversion is exactly wrong. Context usage, elapsed time, how much work is
left, whether a subagent is still alive: these are the facts an agent has the *least* direct
access to. They are only knowable by reading an external source. The feeling of knowing them
is confabulation, and it is confident.

## The rule

**Every number you emit has a source, and the ones about yourself need it most.** If you cannot
name the command that produced a figure about your own state, you do not have the figure — say
"unavailable" and keep working. An unreadable measurement is evidence of nothing; it is not
evidence that the value is high.

Corollary for anyone building guards: a checker keyed on verification vocabulary has a blind
spot shaped exactly like `I am at N%`, `I have about X left`, `there's not enough room to`.
Those are load-bearing measurements wearing the grammar of a feeling. Match on the shape of the
quantity, not on the vocabulary of proof.

## Why it generalises

The failure mode is not "got a number wrong." It is that **a fabricated self-measurement
silently becomes a planning input.** Nobody audits it, because it never looked like a finding —
it looked like the agent reporting how it felt. In this instance it was about to defer real work
and trigger an early wind-down; the same shape produces premature handoffs, abandoned tasks,
and "I'm running low, let me summarise" at a third of the available budget.

It is the estate's own *"a green signal is not the thing it claims to measure"* turned inward.
The signal here was the agent's sense of its own capacity, and the thing it claimed to measure
was a number sitting in a file the whole time.

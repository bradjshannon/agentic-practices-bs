# When a figure stops reproducing, "someone fixed it" outranks "I was wrong"

## Symptom

An agent published a finding: four locales in an evaluation were scoring over *different* case sets,
because 46 entries per translated locale were being silently dropped before a case was ever built.
It went into the issue register, into a status card for the human, into an analysis document, and
into a message to another agent.

Verifying a related change the next day, the numbers no longer reproduced. The same code path over
the same files now reported the locales as **balanced**. The agent worked through three explanations
— an ingest race, a changed tool manifest, duplicate identifiers — disproved all three, and was one
step from telling the human the finding had been an artifact.

It had not. Another session had **fixed the defect that morning**, in a commit whose message said so
in plain words. The finding was correct, was acted on, and the numbers had moved because the problem
was *gone*.

## What actually happened

The agent's mental model of the repository was frozen at the moment it made the measurement. Between
then and the re-check, a concurrent session had read the report, made the fix, and pushed it. Every
input the agent examined — the data files, the code it had written, the manifest — was consistent
with "my analysis was flawed," because the one thing that changed was in a file it had no reason to
re-read.

The retraction would have been worse than a wrong finding. It would have told the human a real
defect was imaginary, *after* it had been fixed on the strength of that finding, and the fix would
have looked unmotivated to whoever found it later.

## The rule

**Before retracting a finding whose numbers no longer reproduce, check whether it was fixed.**

Concretely, in this order:

1. **`git log` the files the finding was about**, restricted to the window between the measurement
   and the re-check. A commit message will often say it outright. This is one command and it comes
   *before* elaborate re-derivation.
2. **Compare against the original commit**, not just the current tree — `git show <ref>:<path>` — so
   you are contrasting like with like rather than measuring today twice.
3. **Only then** consider that the original analysis was flawed.

The ranking matters because the two hypotheses are not symmetric in cost. "I was wrong" is cheap to
say and expensive to be wrong about: it un-motivates a fix that already shipped and teaches everyone
to trust the next finding less. "It was fixed" is cheap to check.

**The tell that you are in this situation:** your finding was *actionable and specific*, it was
communicated to people who could act, and enough time passed for someone to act. Those are precisely
the conditions of a *good* finding — so the better your work, the more likely this failure mode.

## Why it generalises

This is a hazard of every environment where more than one actor can change the substrate: multiple
agents on a shared repository, a teammate who reads your ticket, an automated dependency bump, a
platform that patches itself. The measurement is a snapshot; the world is not obliged to hold still,
and it is *least* likely to hold still precisely when your report was useful.

The general form is that **an agent's model of the world is stale by default, and re-measuring does
not refresh it** — re-measuring tells you the current value, not what changed or who changed it. The
history does that, and history is usually one command away and rarely consulted, because the instinct
after a surprising number is to measure harder rather than to look at what moved.

Corollary: when you *do* confirm a finding was fixed by someone else, say so explicitly rather than
quietly dropping it. The person who fixed it deserves the loop closed, and the record should show the
defect as *resolved* rather than as never-having-existed.

Related: `a-red-signal-deserves-the-same-suspicion-as-a-green-one.md`,
`delegating-a-task-exports-its-stale-premise.md`, `shared-state.md`.

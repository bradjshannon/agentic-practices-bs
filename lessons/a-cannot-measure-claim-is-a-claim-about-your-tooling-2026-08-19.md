# "We cannot measure X" is a claim about your tooling, and gets checked like one (2026-08-19)

## Symptom

An agent wrote a strategy document containing three separate assertions that a thing could not be
measured. All three were false — the capability existed, deployed, in the same repo. Each took
under five minutes to disprove once checked. The project had a tooling inventory written
specifically to prevent this, the agent had read it, and it did not help.

## What actually happened

The document recommended what to build and what to stop doing. Its four recommendations rested on
three claimed limitations:

| Claim written | What existed | Cost to check |
|---|---|---|
| "We cannot score the other server — the harness refuses it by design" | A documented `--allow-s1` override, gated on human authorisation, which stamps the report | one grep |
| "End-of-utterance→first-audio is structurally unreachable" | An emitter deployed months earlier with **2626 records** on the box in question | one grep, one ssh |
| "The real gap is a way to generate real audio turns on demand" | A driver script, frozen 100-phrase case sets per product, and an existing baseline | one `ls` |

The third is the one worth staring at. It was written **in the act of correcting the second.**
Discovering that a false-limitation claim had just been published did not raise suspicion about the
next false-limitation claim in the same paragraph. The correction was treated as a fact to fix
rather than a pattern to check.

The inventory that should have caught this opens with a standing rule — *a discovery about our own
tooling is not a finding* — and instructs the reader to consult it **before proposing to build
anything**. That trigger is the defect. Every one of these three claims was written while
*describing a limitation*, and describing a limitation does not feel like proposing to build. It
feels like reporting the state of the world. The rule fired on an intent the author did not have.

There is a second-order effect that makes this expensive rather than merely embarrassing. A false
limitation does not just fail to inform — it **redirects work**. Two of the four recommendations
were "build this instrument"; had they been actioned, the project would have paid to rebuild two
things it owned, and the rebuilt versions would have competed with the originals as a second source
of truth.

## The rule

**A claim that something cannot be measured, observed, or reached is a claim about your own
tooling, and deserves exactly the same check as a proposal to build tooling.**

Trigger on the **sentence shape**, not on your intent:

> Before writing "we cannot measure X", "there is no way to Y", "X is structurally unreachable",
> or "the gap is that we have no Z" — search the inventory, grep the scripts directory, and state
> the negative **with the population you searched**.

And the corollary the third claim earned:

> **Finding one false limitation is evidence there are others.** Treat the correction as a prompt
> to re-audit every other limitation claim in the same document, not as a single fact to patch.

## Why it generalises

Any inventory, index, or "check here first" convention is guarded by a **trigger condition**, and
the trigger is almost always written as an *intention* — "before building", "before adding a
dependency", "before writing a new script". Intentions are introspective, and introspection about
what you are doing is exactly what fails when you are confident. The author of "there is no way to
Y" does not experience themselves as about to build anything.

So the general form is: **when a safeguard keyed to an intention gets bypassed, re-key it to an
observable — a sentence shape, a file pattern, a command — that does not require the author to
correctly classify their own activity.** The fix here was one paragraph in the inventory's header,
and it converts a rule that fires on self-diagnosis into one that fires on text you can see
yourself writing.

The asymmetry is worth naming too. A false *positive* claim ("we have X") gets caught the moment
someone tries to use X. A false *negative* claim ("we have no X") is never caught by use, because
nobody goes looking for a thing they have been told does not exist — it is caught only by
accident, or by someone who ignores the claim. **Negative capability claims are self-protecting
and therefore need the stricter check**, which is the inverse of how most review attention is
allocated.

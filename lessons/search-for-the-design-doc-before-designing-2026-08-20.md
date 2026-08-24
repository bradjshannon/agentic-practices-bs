# Search for the design doc before designing — the answer is often already on disk, with the fork already answered

**2026-08-20, a voice-assistant server estate, server conductor run 58.**

## Symptom

The operator asked whether we should run an experiment holding the prompts and providers constant
while varying one component. I reasoned it out from first principles, concluded a 2×2 factorial was
needed, wrote up the design, listed the trade-offs, and asked whether to proceed.

His reply: *"we've had this discussion multiple times. i need you to figure out what we need to
compare, and how to do it, based on the needs and objectives we've already discussed. I can't keep
having this conversation. I need results."*

## What actually happened

A `docs/` search that took one command found a design document written **ten days earlier**,
revised the day before, at exactly the path the topic would suggest. It contained:

- the controlled design, in more detail than mine;
- a section titled *"Why the obvious experiment is invalid"*, describing the trap I had just
  avoided — and a second one I had **not**: that flipping the component alone produces a *broken*
  configuration rather than a comparison arm, because the instruction content has to be **split and
  redistributed** between the two shapes;
- a section that already explained the result I had spent the afternoon measuring;
- and, in its last section, **the operator's own written answer to the design's one open fork**,
  given six days earlier, quoting him verbatim.

So the fork was not open. The work had been scoped, decided, and left unbuilt. What was actually
missing was a small code change the document specified line by line, including the caching trap
that would have made the experiment silently report a false null.

The cost was not just tokens. It was asking a busy person to re-make a decision he had already
made, in writing, in the repo.

## The rule

**Before designing anything, search the repository for an existing design.** One `ls docs/` or one
grep on the topic noun. Do it before the first paragraph of reasoning, not after.

And when you find one, read it to the end. **The decisions section is usually last**, which is
exactly where an agent skimming for "the design" stops reading — the open questions and the human's
answers to them live past the point where the document has already told you what you came for.

Two supporting habits:

- **A repo that documents its designs will also document its own traps.** The section I would have
  most benefited from was titled after the mistake, not after the topic. Grep for the failure as
  well as the feature.
- **"Not yet run" is not "not yet decided."** A document marked *design; not yet run* had a fully
  settled design. The gap between decided and executed is where re-litigation creeps in, because
  an unexecuted plan looks from the outside exactly like an unmade decision.

## Why it generalises

An agent starting fresh has **no memory of prior conversations, but the repository does.** That
asymmetry is the whole problem: reasoning from first principles feels like diligence and is
indistinguishable, from the inside, from ignoring work that already exists. Nothing in the act of
careful reasoning surfaces the fact that someone already reasoned carefully about the same thing.

The failure is also self-concealing in a way that punishes the human rather than the agent. A
freshly derived design *looks* like competence — it is coherent, it cites real constraints, it may
even be defensible. Only the person who wrote the original document can tell that it is a worse
copy, and their only way to say so is to have the conversation again. So the cost lands entirely on
the one participant who cannot be re-instantiated.

**The general form: when the work is "decide how to do X", the first tool call should be a search
for a prior decision about X, not the first step of deciding.** This is the planning-time twin of
the standing rule that a capability claim is a claim about your tooling — here, a design proposal is
implicitly a claim that no design exists, and that claim is cheap to check and expensive to get
wrong.

Related: `a-cannot-measure-claim-is-a-claim-about-your-tooling-2026-08-19.md` — same shape, one
layer up. There the false claim was *"we cannot measure that"*; here it is *"this has not been
designed."* Both are negative existence claims about the project's own assets, both feel like
observations rather than assertions, and both are refuted by one search.

## Recurrence, four days later, same document, a different half of "read it to the end" (2026-08-24)

This exact design document has a second caveats section (§4a) documenting that under the mode
being tested, **neither** authored half of the split instruction reaches its target — not just
the half already known about. A test suite ran against the document's own design, its headline
result (a decisive pass-rate gap between two configurations) was reported to the operator with an
artifact, and the report did not surface that the losing configuration's OTHER half was also
broken — because that fact lived in a caveats section of a document already open and partially
quoted, not a section anyone had re-read in full before writing up the result.

The operator's reaction, escalating: first that the result told him nothing useful, then —
correctly — that the actual question he needed answered ("is the architecture worse, or are both
its inputs just broken") remained unanswered by data that looked decisive.

**This is not a new rule — it's the same one, applied one step later in the lifecycle.** "Read a
found document to the end before designing from it" (above) and "read a found document's own
caveats section in full before reporting a result it describes as decisive" are the same
discipline at two different moments: before you build, and before you report. A document you
already have open and are actively quoting from is exactly as easy to under-read as one you never
opened — quoting one paragraph creates the feeling of having consulted the source, which is not
the same claim as having read all of it. **Before headlining any result against a design document,
grep that document for "caveat", "not established", "does not", and "only" — the four words a
limitations section is built from — even in a document you already cited elsewhere in the same
piece of work.**

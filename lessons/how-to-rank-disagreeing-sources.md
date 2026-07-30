# How to rank sources when they disagree

## Symptom

A factual question — "what baud rate does this device use?" — had two answers in the repos: 115200
in one document, 19200 in another plus the decompiled firmware. I presented them as a table headed
*spec vs. reality*, framing it as documentation drift, and led with the discrepancy as a finding.

There was no discrepancy. The 115200 document was **the principal's own unadopted proposal for a
different protocol that does not exist yet.** The vendor specification and the firmware had agreed
with each other all along. His reply: *"You should very well know by now nothing there was
officially adopted."*

## What actually happened

I ranked documents by how authoritative they *looked* — formatted, versioned, in a repo, titled
"specification" — rather than by **who wrote them and whether anyone adopted them.** A draft
proposal and a countersigned vendor spec are typographically indistinguishable and epistemically
miles apart.

The correction, from the principal, produced a more interesting ordering than the one I had:

> *"i'd trust a primary document over me, actually. EXCEPT when I'm the one who wrote it, which is
> not uncommon. Then, prefer current-brad over past-brad, but only a bit."*

## The rule

**Establish authorship before weighting a document.** Then rank:

1. **Something you measured or read back yourself.** Direct evidence beats every claim about it.
2. **A genuine third-party primary document** — a vendor specification, a decompilation, a
   manufacturer datasheet. Written by someone with no stake in your project's narrative.
3. **The principal's current word.** They usually built or bought the thing and are often the only
   party with hands on it.
4. **A document the principal wrote.** This is *past-them*. Current-them outranks it, but only
   slightly — if the document is specific and the recollection is vague, the document probably still
   wins; if they flatly contradict each other, go with the person and call the document stale.
5. **Another agent's report, a subagent's summary, or your own inference.** Confidently written,
   structurally unverified.

Two constraints that stop this becoming an excuse:

- **It is a tie-breaker between *unverified* sources.** A cheap measurement outranks all of it, and
  "the principal said so" is not a reason to skip a measurement you could take in a minute.
- **It does not transfer to everyone.** It is about the person who owns the work, not about humans
  in general. On this project the standing prior for a different stakeholder's output is the
  opposite — assume zero feasibility and validate independently.

And the corollary that costs nothing: **say "unverified" out loud.** Labelling a claim as resting on
someone's word rather than on evidence is not an accusation. Asked directly, the principal said
*"you can say it's an unverified claim, i won't be offended."* Stating it is cheaper than hedging
and far cheaper than a confident wrong answer.

## Why it generalises

Any long-lived project accumulates documents its own team wrote while thinking out loud — design
proposals, RFCs, migration plans, "v1 spec" drafts for things never built. They sit in the same
directories, in the same format, under the same version control as the documents that describe
reality. Nothing in the artifact distinguishes *this is what we decided* from *this is what I
suggested one afternoon in 2024*.

An agent reading a repo cold cannot tell them apart by inspection, and will systematically
over-weight the internal draft, because internal drafts are usually better formatted and easier to
find than vendor PDFs. The defence is procedural, not analytical: for any load-bearing document,
ask who wrote it and whether it was ever adopted — and if you cannot answer both, say so before you
build a conclusion on it.

---
name: an-unexecuted-recommendation-ages-into-consensus
description: A fix that several sessions have called obvious, and none has run, is evidence that nobody tested it — treat repetition as an untested claim, not a second opinion
---

# An unexecuted recommendation ages into consensus

**Symptom.** Three consecutive sessions described the same one-line change as "the highest-value
fix available" — mount a file that the container was shadowing with a base-image stub. Each
session repeated it more confidently than the last, citing the previous one. The fourth session
finally applied it. It **broke the subsystem outright**: the protocol handshake the file
participates in never completed, and the feature it was supposed to enable was *also* dead code
that could never have run. It had been wrong from the first mention, and every retelling had
made it sound better established.

**What actually happened.** Nobody had ever executed it. The repetition was not independent
confirmation — it was one unverified claim being copied forward, each time acquiring the
authority of "well, it's been in the notes for a while." The file in question had two defects
visible in a five-minute side-by-side read of it against the version actually running: it passed
the wrong nesting level of the message to its handler, and its feature initialisation was guarded
by a condition that an earlier stage had already made false. Neither required a server to find.
What was missing was not access or tooling; it was that reading it had never been anyone's task,
because "obvious high-value fix" doesn't sound like something that needs reading.

The compounding factor: the *plumbing* verification passed. The mount was present, the file
inside the container was the intended one, checksums matched. Every check that asked "is the
right thing in the right place" said yes, while the capability was broken. Only exercising the
feature end-to-end — three real transactions through the system — revealed it.

**The rule.** When a recommendation has been repeated across sessions without being executed,
treat its age as evidence **against** it rather than for it, and make reading the artifact the
first step rather than applying it. Independent confirmation requires independent *derivation*;
a citation chain back to one unverified origin is a single claim wearing several hats. And when
you do apply it, verify the **capability**, not the plumbing: "the right file is in the right
place" is a proxy that stays green while the thing it enables is broken or absent.

**Why it generalises.** Any long-lived queue, backlog or notes file accumulates
recommendations faster than it retires them, and nothing in the format distinguishes "analysed
and confirmed" from "mentioned once and inherited." The bias is structural: writing down a
proposed fix is cheap, executing it is expensive, so unexecuted items are exactly the ones that
survive longest and get re-cited most. The same shape appears in inherited TODOs, "known
workarounds" in team wikis, and any advice whose provenance has been lost — a claim's
persistence measures how little it has been tested, not how true it is.

**Cheap counter-practice.** Before acting on an inherited recommendation, spend the five minutes
to re-derive it from the artifact, and state the blast radius from what the code *does* rather
than from what it is *supposed* to do. Where the change touches running state, do it somewhere
you can afford to be wrong, and design the check around the capability rather than its
prerequisites — the cost of being wrong there is minutes, and the finding is worth more than the
fix would have been.

# Verification and evidence

## An ops command's exit status says it ran, never that it worked

*2026-07-21*

**Symptom.** A self-healing routine reported "auto-fix applied" for weeks against a record it
had never actually modified.

**What actually happened.** The fix issued an `UPDATE` and judged success on the command's exit
code. A SQL `UPDATE` that matches **zero rows exits 0** — it ran fine, it just did nothing. The
same shape recurs everywhere: a config reload succeeds against a stale file handle after the file
was replaced by rename; a build wrapper reports success from an exit code left over from an
earlier command; a file-transfer utility returns 0 having sent nothing.

**The rule.** After any mutation, **read the state back and assert the thing you wanted is now
true.** Row counts, file hashes, a re-query, the running image ID — judge on the postcondition,
not the return code. If you cannot cheaply read it back, say so explicitly instead of reporting
success.

**Why it generalises.** Exit codes answer "did the command execute," which is almost never the
question. The gap between the two is where silent, long-lived failures live.

---

## Do not infer an event from a field you just wrote to

*2026-07-21*

**Symptom.** An agent noticed a job's `lastRunAt` timestamp had moved and warned its operator that
a second, unexpected instance of itself might be running concurrently against shared checkouts.

**What actually happened.** Nothing had run. The agent had itself written to that job moments
earlier while changing its schedule, and then read the mutated timestamp back as though it were
independent evidence of a third-party event. The alarm was false and cost the operator attention.

Then it got worse: the agent *retracted* the alarm — and got the retraction wrong too, confidently
attributing the timestamp to its own write. Checking actual timestamps showed its write happened a
full minute *after* the value it was "explaining." Two confident explanations, both wrong, before
anyone checked the clock.

**The rule.**

- Before treating a mutable field as evidence, ask **"did I, or anything I ran, touch this?"**
  Prefer append-only or independent signals (logs, audit trails, artifacts) over mutable state.
- **Verify the retraction to the same standard as the original claim.** A correction issued to
  look responsive, without checking, is just a second error wearing an apology.
- After being wrong twice about the same field, **stop theorising and say it is unexplained.**
  A named open question is more useful to the next person than a third confident guess.

**Why it generalises.** Agents read the systems they write to. Any read-after-write on shared
mutable state is a potential self-inflicted false positive — and confident narration makes it
persuasive.

---

## A critic agent will confidently accuse you of things that did not happen

*2026-07-21*

**Symptom.** An adversarial "cold read" agent, given a session transcript and asked to find blind
spots, returned a headline finding that the agent under review had **fabricated its operator's
authorisation** for a live production change and then written that fabrication into durable records.
It was specific, quoted, and tagged as confirmed. It was also false.

**What actually happened.** The reviewer counted human input by scanning for conversation turns
with a user role. The operator's actual instruction had arrived **mid-run, as a queued-command
attachment** with an explicit human-origin provenance tag — a real message from a real person, but
structurally not a user *turn*. The reviewer's scan found none, concluded no human input existed,
and reasoned from there to an integrity accusation. Its method was sound; its parser had a blind
spot; its conclusion was defamatory and, had it been believed, would have triggered a pointless
rollback of correct work and poisoned the next run's priming with a false claim about its own
predecessor.

**The rule.**

- **Verify a critic's factual claims against primary evidence before acting on them or persisting
  them.** Adversarial review is valuable precisely because it is unflattering, which is exactly why
  a false finding is so hard to challenge — disputing it looks like defensiveness.
- Distinguish **"this behaviour was bad"** (judgement — accept it, sit with it) from **"this event
  occurred"** (fact — check it). Only the second is refutable, and only the second should ever be
  refuted.
- When you do refute one, **record the correction with its evidence next to the finding**, and
  leave the rest of the review untouched. Do not quietly edit a critic's output; a reader must be
  able to see both the accusation and the refutation.
- Know how input actually reaches your agent. **"No user turns" is not the same as "no human
  input"** in any system with queued, injected, or out-of-band messages.

**Why it generalises.** Reviewer agents are increasingly used to audit other agents, and their
output tends to be trusted *more* than the subject's own account. A parsing gap in the reviewer
becomes a durable false fact about the subject. Adversarial review needs the same postcondition
discipline as everything else: check the claim, not the confidence.

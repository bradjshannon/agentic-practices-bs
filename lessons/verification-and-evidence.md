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

---

## A green signal is not the thing it claims to measure

*2026-07-21*

**Symptom.** Six separate incidents, wearing six different costumes, all with the same root shape:

- A dashboard showed a server **GREEN** off a four-day-stale cache while that server's patches had
  in fact been wiped — a live defect serving traffic behind a healthy badge.
- A post-deploy audit **fired on schedule**, but its job's `if:` guard evaluated false and the job
  skipped. The workflow ran; the check did not — and the self-heal built into that check therefore
  never ran either, which is *why* the patch above stayed wiped.
- A port-forwarding rule was **present in the config table but its listener was never bound.** The
  far end polled a refused port for hours while every configuration read looked correct.
- A service **acknowledged requests in seconds while every actual task it was asked to do failed.**
  It looked healthier than a dead one.
- A mesh-VPN `status` command reported a peer **offline while that peer was actively connected**,
  driving three wrong diagnoses and one pointless reboot of a working machine.
- A file-transfer utility, a message-send CLI, and a build wrapper all returned **exit 0 having done
  nothing** (the last from a stale exit-code variable left over from an earlier command).

**What actually happened.** In every case, **configuration presence — or a cheap status endpoint —
stood in for the capability itself.** Nothing verified that the configured thing was bound, that the
check actually executed, that the acknowledging service could perform work, or that the bytes moved.
The signal was real; it simply was not measuring what everyone read it as measuring.

This class is more expensive than a plain outage, because a visible failure earns attention
immediately while a false green consumes attention — people debug the wrong box, reboot healthy
machines, and trust a stale verdict indefinitely.

**The rule.**

- Ask **"what would be observably true if this were actually working?"** — then observe *that*.
  Probe the data path: request the endpoint, re-read the artifact inside the running container, diff
  the served asset, count the rows. Not the status that claims it.
- **Never accept a liveness or status API as proof of liveness.** It is a claim, not a measurement.
  Prove it with the path you actually depend on.
- **A cached verdict must carry its own timestamp, and consumers must check it.** "Green" with no
  freshness is unfalsifiable.
- When you *build* something that answers requests: **self-test the advertised capability at startup
  and refuse to serve if it cannot deliver**, and **log the configuration it actually resolved.** One
  such log line would have ended a multi-hour, multi-agent root-cause argument permanently — the
  cause stayed unknown for exactly one reason: nothing recorded what the process actually got.

**Why it generalises.** Every layer offers a cheap health signal, and cheap signals get adopted
precisely because they are cheap. The gap between "the config says so" and "the capability works"
is where the most expensive outages hide, because everything on the dashboard is green while
nothing works.

---

## "Received" is not "visible": two consumers, one documented sink

*2026-07-21*

**Symptom.** An operator asked why his instructions had been ignored. The agent checked its inbox
file, found nothing new, and reported — twice, confidently — that the messages had never arrived.
Then the operator asked a question that broke the story open: *if messages weren't arriving, how did
the machine receive a task, flash a device over USB, and send the reading back?*

**What actually happened.** The system had **two independent consumers** of the same message stream:

- a **worker**, which acted on actionable requests and logged everything it saw to its own log file;
- a **journaller**, which was the only thing that wrote the inbox file every convention actually read.

The journaller had been dead for five days. The worker was fine — which is why executable requests
were serviced perfectly and the channel looked healthy. But the worker's default handler for
*human-readable* messages only logged them. So those messages were received, parsed, processed, and
written to disk **in a file nobody reads**. Grepping the worker's log found every "missing"
instruction verbatim. **Nothing was ever lost or dropped.**

The agent's own error is worth naming separately: it *established* "the inbox file stopped growing"
and *asserted* "the messages never arrived." Those are different claims, and it substituted the
convenient one.

**The rule.**

- **If two components can consume the same input, they must write to the same sink** — or the one
  that doesn't creates a permanent blind spot that only appears when the other dies. Make every
  consumer journal to the canonical store, idempotently (dedupe on the message id, so a healthy
  system doesn't double-write).
- **A default handler that only logs is a dead end.** "We log it" is not "someone will see it."
  Logging to a path with no reader is indistinguishable from discarding.
- **A reader of a local cache must be able to detect that it is behind the source.** Any "nothing
  new" that cannot tell *empty* from *disconnected* will eventually report silence during an outage
  — and it will be believed.
- Before concluding that input never arrived, **check every sink that could have received it**, not
  just the one you normally read.

**Why it generalises.** Fan-out to multiple consumers is standard — a worker plus an audit log, a
processor plus a UI feed, an agent plus a transcript. The moment their sinks differ, "delivered"
and "visible" come apart, and the gap is invisible from the side you happen to be looking at.

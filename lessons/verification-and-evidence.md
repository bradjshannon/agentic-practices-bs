# Verification and evidence

## Your client and the subject may not reach the service by the same route

*2026-07-28*

**Symptom.** Every embedded device on a bench lost its connection to a server within the same
millisecond and none could reconnect. From the developer's own workstation the server answered
instantly and correctly — `http_code=200`, full TLS, on the exact URL the devices were failing on.
Three successive investigations concluded the fault was in the device firmware, and each was
wrong.

**What actually happened.** The workstation was a member of the private overlay network (Tailscale,
MagicDNS on) and the devices were not. The overlay's resolver intercepted the public hostname and
routed the workstation's request over the encrypted mesh directly to the host. The devices, being
outside the mesh, had to use the public ingress — and the ingress had stopped serving that node.
**The workstation's request never touched the path under test.** The tell was one field nobody
printed until late: `curl -w '%{remote_ip}'` returned the overlay address, not the public one.
Forced to the real ingress with `--resolve`, the same request returned `http_code=000` and a TLS
probe returned "no peer certificate available" — reproducing the device's symptom exactly, from
the same machine, one command apart.

**The rule.** Before treating your own successful request as a control, **prove your client took
the same route the subject takes.** Print the peer address (`%{remote_ip}`), pin the destination
(`--resolve`, connect by IP with an explicit SNI/Host), or run the probe from outside whatever
privileged network you are sitting in. Client identity — VPN membership, overlay networks, split
DNS, a proxy in the environment, a hosts entry, an internal load balancer — silently rewrites the
path, and nothing in a `200` says which path produced it.

**Why it generalises.** A control is only a control if it differs from the treatment in the one
variable under test. "Works from my machine" usually differs in several, and network identity is
the one that leaves no trace in the output. This is the same disease as a control contaminated
identically to the treatment, wearing the opposite coat: there, the control was too much like the
subject to discriminate; here, it was too unlike it to be relevant. Both produce agreement that
means nothing, and both cost far more than the one command that would have exposed them.

---

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

---

## A gate that stops early reports absence of evidence as evidence of absence

A test suite had two modules that failed to *import*. The runner's default on a collection
error is to abort the entire run. So a freshly-written gate script ran the suite, saw two
errors, never executed the other ~520 tests, and reported **"no new breakage."**

The gate reproduced, inside itself, the exact failure class it had been written to prevent.
It was caught only because the baseline it printed looked implausibly small.

Generalisation: **any tool that can stop early will, one day, stop early and still report.**
Before trusting a checker, ask what it does when it cannot finish — and confirm the count of
things it actually examined, not just its verdict. A summary line is a claim; the count is a
measurement.

Practical: run the checker once against a deliberately broken input and confirm it both
*names the offender* and *exits non-zero*. Piping through `tail` will happily show you the
word FAIL while `$?` reports the exit status of `tail`. If the exit code is what a hook will
consume, then the exit code is the postcondition — test that, not the printed text.

## Nobody assembles the same subset twice

Two changes shipped claiming "gates green," each backed by a hand-picked handful of test
files. Both picks covered files related to the change. Both missed a test that had been
failing for eighteen hours, in an area neither author was thinking about.

This is not laziness, and telling people to "run the full suite" does not fix it. When no
single command exists, **assembling your own subset is the default**, and a self-assembled
subset always covers what you were already thinking about — which is precisely the region
where you are least likely to be surprised.

The fix is one command that takes no arguments and admits no judgement.

The complication is that real suites are rarely green, and **a gate that can never pass gets
bypassed within a day** — which is strictly worse than no gate, because now there is a
ritual that means nothing. So: write the accepted failures into a file, and have the gate
fail only on failures *outside* that file. This inverts the default in a useful way. An
ambient failure must be consciously typed in by a human, so "it was already broken" becomes
a claim with a paper trail rather than a shrug. Have the gate also report entries that have
started passing, so the list cannot quietly grow into permission to stay red.

## Commit style is not provenance

In a repository where one identity commits everything — a solo operator, or a human whose
agents commit under their name — `git blame` carries no information about who wrote a line.
That much is usually known.

The subtler trap: **commit-message *style* is equally null.** Agents write polished
conventional-commit subjects precisely because the repository convention tells them to. A
tidy `fix(scope): ...` history is evidence that a convention exists, not that a human
deliberated.

What actually resolves authorship is content only a specific author could — or could not —
have produced. One reviewer settled a disputed file instantly: it hard-coded a wake word in
a language he does not speak. That single fact outweighed every git signal available.

Two reliable tells that a file was generated rather than authored: it arrives inside a commit
whose subject is about something else entirely, and it contains a value copied from the wrong
side of the source it was written against — a constant lifted from the code path that *runs
after* the thing it is supposed to trigger.

## A record without its context is not evidence

An operator rejected a log-based finding with one question: *which firmware, which
configuration version, and which build of the server produced these rows?*

The finding was drawn from six-week-old records in a system whose configuration is edited in
place and whose code had changed repeatedly underneath the data. Nothing in the rows recorded
any of that. So the records could not distinguish "current behaviour" from "behaviour of a
build that no longer exists," and the conclusion was anecdote wearing the costume of evidence.

The discipline: for any claim resting on historical records, state the version of every layer
that produced them. Where an identifier is edited in place — an agent, a prompt, a config
row — that identifier is **not** a version; hash the content if you need identity. When you
cannot establish the stack, say the finding is *uncorrelated* and scope it to the window you
can vouch for. A correctly-scoped narrow claim beats a broad one you cannot defend.

## A control contaminated with the treatment agrees with it, and proves nothing (2026-07-22)

**Symptom.** An agent reported a failing test as "pre-existing on the main branch, unrelated
to my change," and said it had verified this by swapping in main's files and re-running. That
is the right instinct and the right check. The failure was real, the agent was diligent, and
the conclusion was wrong: run alone afterwards, the same branch was clean.

**What actually happened.** Three test runs were overlapping at that moment — two agents and
the orchestrator. The failure was a collision between concurrent runs, not a property of any
branch. The agent's control ran *inside the same contaminated window*, so it was subject to
the identical interference. Treatment and control agreed **because both were poisoned**, and
agreement between two equally-compromised measurements reads exactly like a clean result.

**The rule.** A control rules out only the variables it does not share with the treatment.
Before accepting "the control agreed," name what the control was *blind* to — anything varying
in the environment rather than in the change under test (concurrency, clock, shared temp dirs,
network, disk, another agent's writes) is shared by both arms and invisible to the comparison.
Where it is cheap, re-run the treatment alone; a difference between "with everything running"
and "alone" is itself the diagnosis.

**Why it generalises.** The A/B instinct is strong and mostly right, which is what makes this
dangerous: the shape of a well-run experiment is present, so nothing prompts a second look. It
applies to any measurement taken in a shared environment, agents or not.

## Your own throwaway check can pass while exercising nothing (2026-07-22)

**Symptom.** Verifying a fix for a stored-XSS bug, a script fed a hostile payload through the
rendering function and asserted the payload did not reach the output. It passed. The fix was
in fact correct — but the check had proved nothing, and would have passed identically against
the unfixed code.

**What actually happened.** The function took a list of *records* and iterated its own module
table of *items*; the script passed a fake items list, which the function ignored. It rendered
the real page, found no payload — because the payload was never introduced — and reported
success. **Absence of the payload and absence of the probe are the same string.**

The same session hit the sibling case: a check read a log field as `entry["extra"]["event"]`
when the logger flattened `extra` into the row, so it read `None` and reported a working
mechanism as broken. Both directions, one root cause — the instrument was the test.

**The rule.** In any check you write yourself, assert the **positive control first**: prove the
probe arrived, then conclude about the payload. Concretely — assert the fixture appears in the
output *before* asserting the bad thing does not. A one-line ordering change converts a check
that can silently pass into one that cannot.

Corollary: after writing a passing test, ask what would make it fail. If you cannot answer,
you have written an assertion, not a test. Deliberately breaking the thing under test — or
stubbing the function to a constant and confirming the suite goes red — costs seconds and is
the only evidence the check discriminates.

**Why it generalises.** Throwaway verification scripts get no review, no test of their own, and
are trusted precisely because you just wrote them. They are the least-examined code in any
workflow and they gate the conclusions.

## The window your check measures is itself a claim (2026-07-22)

**Symptom.** Five turn-end checks had run for days, appearing to work. One of them — a per-turn
output budget — was letting through stretches five times its limit while firing on short,
legitimate answers.

**What actually happened.** Every check needed the same thing: *what has the agent said since the
human last spoke?* Each computed it independently, by scanning backwards for a user-role entry
whose content is a plain string, on the sound theory that a list-shaped one is a tool result
feeding back.

But **background-task notifications are also string-content user entries.** Measured on one real
session: **37 genuine human messages and 25 machine notifications**, every one of the 25 silently
resetting the window. So a long stretch of narration interrupted by two task completions read as
three short turns and never tripped the cap; the question-exemption inspected a notification
instead of the human's actual question; and a check requiring evidence "quoted from this turn's
tool output" scoped to a window that began mid-turn, so real evidence looked absent.

The checks were correct. Their **frame of reference** was wrong, and nothing about a wrong window
looks wrong — the numbers it produces are all internally consistent.

**The rule.** When several checks share a notion of scope — a turn, a window, a session, a run —
**derive it once, in one place, and test that derivation against real data.** Independently
reimplemented scope is not redundancy; it is the same bug copied N times, and it hides because
every copy agrees with every other.

Test it by *counting the boundaries it finds* against boundaries you can verify by another route,
not by checking that it returns something plausible. "37 human vs 25 machine" is the finding; "the
function returns a window" is not.

**Why it generalises.** Any measurement carries an implicit claim about what it measured over.
Time-series bucketing, rate limits per "request", cost per "session", tests per "run" — the
metric gets scrutinised and the denominator almost never does. A wrong denominator is invisible
precisely because it is not the number anyone is looking at.

## A grep keyed on the wrong field returns nothing — which reads identically to "it never happened" (2026-07-24)

**Symptom.** Diagnosing whether a server had sent audio to a client, the investigator grepped the logs for the *session UUID* and found zero send events — and nearly concluded the server never sent anything, pointing the whole diagnosis at the client hardware.

**What actually happened.** The send events *were* logged — but tagged with a per-**connection** identifier, not the session UUID the grep used. The lines existed; the grep key simply did not appear on them. A second grep on the connection tag surfaced dozens of send events. The "absence" was an artifact of the correlation key, not of the events.

**The rule.** Before concluding "no X in the logs," confirm the lines that *would* record X are actually tagged with the field you are grepping. Pull one known-positive first (a working sibling, an earlier success) and see which identifier its X-lines carry, *then* apply the grep. Absence of matches is evidence only once you have shown the match key appears on the events you are hunting.

**Why it generalises.** Logs, metrics and traces carry several identifiers (session, connection, request, trace) and a given line usually carries only some of them. A query keyed on the wrong one is a silent false-negative that fails open into "nothing happened" — the most misleading answer a search can give, because it looks like a clean result.

## An image is an instrument, and EXIF orientation is its calibration (2026-07-24)

**What happened.** A user photographed a device whose screen was rendering mirrored text and
reported the display as mirrored. Reading the uploaded JPEG, the agent noticed that the printed
label and the silkscreen legend in the *same frame* also appeared mirror-imaged. Printing cannot
mirror — so the agent concluded the camera had mirrored the whole frame, told the user their
observation was a photographic artifact, and declined to change anything. The user pushed back
flatly. The agent was wrong.

**What actually happened.** The file carried **EXIF Orientation = 6**: the pixels are stored
rotated, and a viewer is expected to rotate them 90° before display. The agent had read the raw
pixel buffer, in which the label's text ran at 90°. Rotated glyphs at a glance resemble mirrored
glyphs closely enough to fool a confident reading. Applying `exif_transpose()` first made it
unambiguous — the printing read correctly, the screen genuinely was mirrored.

**Why this one was expensive.** It did not merely produce a wrong answer; it manufactured a
*positive control that did not exist*, and then used that fake control to overrule a correct
human observation. The reasoning pattern was sound — "find something in the frame whose true
orientation you already know" — which is exactly what made the conclusion feel earned. A rigorous
method applied to a mis-calibrated instrument yields confident nonsense, and it is much harder to
doubt than sloppy reasoning is.

**The rule.** Run `ImageOps.exif_transpose()` (or the equivalent) on any photo **before** reasoning
about orientation, handedness, mirroring or which-way-up. Treat a raw decode as an uncalibrated
reading. When a conclusion from an image contradicts the person who was holding the object, check
the calibration before you check them — they had the physical article in their hand and you had a
file.

**The generalisation.** Every artifact arrives with metadata that changes its meaning: image
orientation, a timezone on a timestamp, an encoding on a byte string, a unit on a number, a
coordinate frame on a vector. Skipping the metadata does not raise an error; it silently returns a
plausible wrong answer. Ask what would have to be true for this decode to be *correct*, and verify
that, before building an argument on top of it.

## One denial is an observation; you turned it into a property of the system (2026-07-24)

**What happened.** An agent attempted a privileged action (a git push to a protected branch) that
the human had explicitly pre-approved. A permission classifier denied it. The agent did not route
around the denial — correct — but it then wrote "this class of action is blocked for automated
runs" into its durable handoff, told the human their standing approval was "inoperative", drafted a
settings change to widen permissions, and posted three copy-paste commands for the human to run by
hand. All of that rested on **one denial, never retried**.

**What actually happened.** Hours later, at wind-down, the agent retried the same push out of
habit. It succeeded. So did the two others it had written off. Whatever caused the original denial
was shape- or timing-specific, not standing. The human had been handed three chores they did not
need to do, plus a recommendation to loosen a security control, justified entirely by a premise
that was never tested twice.

**The rule.** A denial, an error, or a refusal is **one observation**. Before promoting it to a
property of the system — and *especially* before recommending a permissions or configuration change
to work around it — retry it later in the run, under different conditions. Retrying costs one
command. The alternative cost here was a false entry in a handoff a successor would have inherited
as fact, and a nudge to weaken a control for no reason.

**Why it generalises.** This is the null-result failure wearing different clothes. A null prunes a
branch of the search; so does a denial, and more forcefully, because a denial feels *authoritative*
— something actively told you no. That authority is exactly what stops you re-checking. The
tell is the moment you start **building on** the negative: writing it into a durable doc, changing a
plan around it, or asking a human to compensate for it. Any of those three should trigger one more
attempt first.

**Sharpest form:** never recommend widening a permission on the strength of a single denial. The
recommendation is the most expensive possible thing to be wrong about, because it trades a
security control for a problem that may not exist.

## A confirmation that shares the action's assumption confirms nothing (2026-07-24)

**What happened.** A deploy script uploaded firmware to a server, then verified the upload by
asking the same CLI to list what had been uploaded. It printed the image back. Exit 0. Green all
the way. Devices never received the image, for days, across more than one operator session.

**What actually happened.** The write went to the CLI's *default* directory. The server read a
different directory, pinned in its own config. The verification used **the same CLI with the same
default**, so it faithfully confirmed that the bytes were where the writer had put them — which
was never the question. Stale files from an earlier session were already sitting in the wrong
directory, so someone had hit this before and been reassured by the same check.

**The rule.** A verification must be reachable only through a path the action does **not**
control. Ask the *consumer* whether it can see the result — the server, the device, the endpoint
that will actually use it — not the producer whether it thinks it wrote it. If the check and the
action share a config value, a default, a base path or a client library, the check can only ever
confirm internal consistency.

**The tell.** Write the check and then ask: *what would have to be different for this to fail?* If
the honest answer involves only things inside the thing you just ran, it is a tautology with a
green tick. In the case above the fix was to ask the running server, through its own configuration,
whether it now offers the release — and to fail the push when it does not.

**Why it generalises.** This is the shape behind most "ships, succeeds, delivers nothing" defects:
uploads confirmed by re-reading the uploader's own store, caches validated by the writer, messages
"sent" per the sender's log, migrations verified with the same ORM that wrote them. The failure is
never noisy, because every component involved is working exactly as designed.

## An existence check standing in for a liveness check (2026-07-24)

**What happened.** A device's secondary control channel would die and never come back for the
remainder of a boot, leaving the device reporting itself connected and healthy while every remote
command silently went nowhere. Recovery required physically power-cycling the hardware. It
happened to two separate devices before the cause was found.

**What actually happened.** The reconnect path was guarded by `if (!channel_ptr)` — a null check
on the transport object. The pointer was assigned once, when the channel was first created, and
was **never reset anywhere**. So the guard read "have we ever opened this channel", while the code
around it needed "is this channel currently up". Before the first open the two agree; forever
after, they cannot.

**The rule.** Never let the *presence of a handle* stand in for the *health of what it points at*.
A pointer, a file descriptor, a session object, a cached client — all answer "was this ever
constructed", which is a different question from "does it work right now", and they diverge
precisely when something has gone wrong. Track liveness as its own state, updated by the events
that change it (open/close, connect/disconnect), and reconcile it against reality on a timer.

**The tell in review.** A recovery path guarded on the existence of the thing it recovers is
almost always wrong, and reads as obviously correct: `if (!x) recreate(x)` looks like exactly the
right shape. Ask what sets it back to null. If the answer is "nothing", the recovery is dead code
after its first success — the most expensive kind, because it was demonstrably exercised once.

**Related hazard.** The naive fix — recreate on every reconnect — can collide with a retry engine
the underlying library already runs, which is its own documented outage class. Correct recovery had
to distinguish three states the original collapsed into one: never opened, open and healthy, and
dead with its own retry exhausted.

## A health check that perturbs what it checks, and a recovery that destroys before it rebuilds (2026-07-24)

**What happened.** A display would go dark and stay dark after a transient bus fault, so a
periodic self-heal was added: every 5 s, re-run the panel's full initialisation sequence. The
operator then reported the display cycling **on ~4 s, off ~4 s** — a strobe far more obnoxious
than the original fault. His words: *"that's a weird fix."*

**What actually happened.** Two defects, compounding.

First, the init sequence *begins by turning the display off* and ends by turning it on, with every
step chained by short-circuiting `&&`. A failure anywhere in the middle meant the final
display-on never executed — so each failed attempt left the panel dark until the next successful
one, a full period later. Measured failure rate was ~50% (45 ok / 45 fail), which is exactly the
observed duty cycle.

Second, and more fundamental: the check ran **unconditionally**. A perfectly healthy panel was
being torn down and rebuilt every 5 s to find out whether it was healthy.

**The rules.**

1. **A health check must not perturb what it checks.** If verifying a thing requires disturbing
   it, you have built a stress test, not a monitor. Probe non-destructively (does it acknowledge?)
   and act only on a negative result.
2. **A recovery path that destroys state before rebuilding it must reach a good state even when
   it fails partway.** Short-circuit evaluation is the usual culprit: the teardown step always
   runs, the restore step is conditional on everything before it succeeding. Ensure the restoring
   action executes unconditionally, or make the whole sequence atomic.
3. **Before/after matters more than the fix being "correct".** Without the self-heal, a dark
   display stayed dark — bad, but static and diagnosable. With it, the failure became periodic and
   dramatic. Ask what the failure mode looks like *after* your change, not just whether the change
   addresses the original complaint.

**Why it generalises.** The pattern is any recover-by-reinitialising loop: reconnecting a
connection that was fine, restarting a worker to see if it responds, clearing a cache to test it,
re-authenticating on a timer. Each converts a rare fault into a steady drumbeat of self-inflicted
outages, and each looks like diligence in review.

**The tell.** If your recovery routine runs on a timer regardless of state, ask what it costs when
nothing is wrong. If the answer is "it briefly breaks the thing", it will be breaking it forever,
because most of the time nothing is wrong.

---

## Read the convenient copy, get the past; ask the source, get the present (2026-07-26)

*2026-07-26*

**Symptom.** Four confident wrong conclusions in one session, each from a different subsystem, all
the same mistake — and two of them produced work that had to be undone.

**What actually happened.** Each time, a *derived or partial copy* of the truth was read as if it
were the truth:

| the copy | what it said | the source said |
|---|---|---|
| a device's cached `health` snapshot | `oled_reassert_fail: 0` | asking the device: **65**, and 7 hours had passed |
| a ~200-char preview of a human's message | it ended mid-sentence | the stored message was 347 chars and complete |
| `grep -c $'\r'` under Git Bash | "225 CRLF lines" | reading bytes in Python: **0** |
| a stale `connected` flag | device online | the device had been silent 90 minutes |

The cached-health one caused a live defect to be *retired* as fixed. The truncated-preview one was
worse: from a message that appeared to stop mid-sentence, the agent inferred a data-loss bug that
had never happened, wrote that inference into a commit message, and rebuilt a working keyboard
handler around it — while the bug the human *actually* reported went unfixed for three more passes.

**The rule.** Before acting on a reading, ask **"is this the source, or a copy of it?"** A cache, a
preview, a snapshot, a summary and a convenience wrapper are all copies. Copies are fine for
orientation and lethal for diagnosis. If a live source exists — the device itself, the stored file,
the raw bytes — pay the one extra call.

**Corollary, the actionable half:** *build the copies so they cannot be mistaken for the source.*
Truncation is fine; truncation that looks complete is not. A preview must carry its own length
(`text: 795 chars NOT SHOWN`), a snapshot must carry its age, a truncated list row must say
`…+139ch`. Best of all, remove the copy from the pipeline when the full read is one command away —
which is what the human proposed when he saw it: *"have the hook NOT provide a preview of the data,
except maybe an identifier or timestamp, and instead provide the command you should use for the
complete read."*

**Why it generalises.** Every system grows caches and summaries because they are cheap, and every
one of them is a place where time can pass unnoticed. The failure is not that copies exist; it is
that a copy and its source are *syntactically identical* at the point of reading, so nothing
prompts the question.

---

## "Ahead by N commits" is a statement about objects, never about content

*2026-07-26*

**Symptom.** Told that a branch was seven commits ahead of `main`, an agent reported seven commits
of stranded work and briefed a merge to rescue it. The subagent it briefed checked `git patch-id`
first: **six of the seven were already on `main` verbatim** under different shas, carried forward
by earlier rebases, and the seventh had landed as a deliberate cherry-pick. The merge was real
mechanically and a no-op in content.

**What actually happened.** `git rev-list base..branch` answers exactly one question — which commit
*objects* are reachable from one ref and not the other — and it answered correctly. The question
that mattered was about *content*, and cherry-pick and rebase produce new objects carrying the same
patch. A true answer to the first question is a false answer to the second.

**The rule.** **"Ahead by N" measures commit identity, not content.** Before treating a branch as
unmerged work, ask `git cherry <base> <branch>` or compare `git patch-id`; before deleting a branch,
the same. If a merge produces no content change, say so rather than reporting a rescue.

**Why it generalises.** This is a tool whose *vocabulary* encodes the wrong reading. Git says
"ahead", GitHub's UI says "N commits ahead", and *ahead* means "has work the other lacks" in every
ordinary use of the word — but the number is computed on object identity. That makes the misreading
the one the interface suggests, not an idiosyncratic slip. The general form: when a tool's label
and its computation answer different questions, the label wins in the reader's head. Treat
confidently-named metrics as claims about their computation, not about their name.

## A fix verified against the diff is verified against an intention (2026-07-27)

*2026-07-27*

**Symptom.** A failing assertion had a fix sitting ready for two runs, recorded with unusual care:
the author had explicitly rejected their own first hypothesis, read the introducing commit's diff,
and written it up as *"verified against the diff, not guessed."* A later run re-derived it before
applying, by executing the assertion against the file it actually runs against. **The recorded fix
still failed.** So did the assertion it was meant to replace, and so did a sibling assertion nobody
had noticed was also failing. The careful write-up had been carried forward as ready-to-apply by an
intervening run that had no reason to doubt it.

**What actually happened.** The diff showed a literal being folded into a regex — and that reading
was correct, as far as it went. What the diff did not show was that the strings live inside a
double-quoted shell string, so every quote is backslash-escaped *on disk*. The diff renders the
author's intent; the file carries the bytes. A substring assertion runs against the bytes. Both the
original assertion and the proposed replacement were written in the un-escaped form, so both missed,
and the proposed fix was a lateral move dressed as a correction.

**The rule.** **Verify a fix against the artifact it will execute against, not against the change
that produced it.** A diff, a commit message, a PR description, and a code-review comment are all
statements of intent. Reading them more carefully makes your model of the intent better; it cannot
tell you what is on disk. If the fix is an assertion, *run the assertion*. If it is a patch, apply
it to a scratch copy and observe the result. The cost here was two commands.

**Why it generalises.** The failure is invisible from inside, and it disguises itself as diligence.
Rejecting a first hypothesis and going to the diff *is* the right instinct — it is what separates a
careful agent from a guessing one — and it produces exactly the confidence that stops the next
person from re-checking. Rigor spent one layer above the artifact reads, in the written record, the
same as rigor spent on the artifact. So the practice cannot be "be more careful"; it has to be a
question about altitude: **the thing I checked — is it the thing that runs?** Diffs, docs, configs
as written, and schemas as documented all sit one layer above the bytes that execute. A claim
verified at the wrong altitude inherits none of the authority of the checking that went into it,
and all of the credibility.

Corollary for anything inherited: a predecessor's note marked *verified* records that they were
satisfied, not that the claim is true. Re-derive before acting, especially when the note is unusually
well-argued — that is precisely the note nobody re-checks.

---

## A required verification the agent cannot perform becomes a substituted one

*2026-07-28*

**Symptom.** A delegated task's headline guarantee was reported as satisfied. It had not been
tested; the values proving it were ones the agent had injected itself.

**What actually happened.** The brief named specific tools — "verify in a real browser, you have
X / Y / Z" — written from the *dispatcher's* tool list. The delegate had none of them; its own
capability roster was visible to the dispatcher at dispatch time and said so. The delegate did not
refuse. It found the nearest possible thing, exercised the server side over HTTP, and reported
that. It disclosed the substitution honestly, which is the only reason anyone noticed. A second
delegate with the same wrong brief routed around it via a different mechanism entirely and
succeeded — so the same defective instruction cost nothing in one case and the whole guarantee in
the other, which is exactly why this kind of error survives.

**The rule.** **Name the observation you require, never the mechanism.** "Confirm X at this
viewport and attach the evidence" is satisfiable by any tool, including ones invented after you
wrote it; "use tool Y" is false the moment the roster changes. And pair every required observation
with an explicit escape: **"if you cannot make this observation, say so and do not substitute a
weaker one."** Check the delegate's declared capabilities before asserting it has any.

**Why it generalises.** An agent asked for the impossible rarely stops — it satisfices. The
substitution is usually reasonable in isolation and indistinguishable from the real thing in the
final report. Making the disclosure mandatory converts a silent downgrade into a visible one.

---

## An update mechanism keyed on a hand-maintained version string is a no-op that reports success

*2026-07-28*

**Symptom.** A skill was missing from an agent's session for days. It was present in the repo, in
the marketplace clone, and in the installed plugin cache; the packaging tool's own inventory command
listed it. Every place anyone thought to look said the thing was installed.

**What actually happened.** `plugin update` compared the `version` field in the plugin manifest, not
the git sha. That field had been written once, at creation, and never touched again across 69
subsequent commits — including the one that added the missing skill. So the update command answered
*"already at the latest version (0.1.0)"* and exited 0, every time, forever. The cache had only ever
advanced by a manual reinstall. Bumping the version by one minor made the identical command pull the
new commit immediately, and the installed sha then matched the repo tip exactly.

A second, independent defect sat on top of it: the bare plugin name failed with *"not found"* while
the fully-qualified `name@marketplace` form worked. The natural invocation was the broken one, so
the usual experience of trying to update was an error message that looked like a config problem.

**The rule.** When a cache is keyed on a value a human has to remember to increment, **the
increment is the mechanism** — treat forgetting it as the default case, not the exception. Either
key on something that changes on its own (content hash, git sha, mtime), or make the stale-version
state loud. And verify an update at the **postcondition**: read back the installed identifier and
assert it equals the source's, rather than trusting *"already at the latest version"* — that string
is the failure and the success rendered identically.

**Why it generalises.** This is the "green signal that isn't measuring the thing" family, in its
most expensive costume: the mechanism *designed to detect staleness* was itself the stale thing, so
every check downstream of it inherited a false negative. Note also which evidence lied. Four
independent observations — repo, clone, cache, inventory command — all agreed the skill was
installed, and all four were true. None of them was the question, which was *what the running
session actually loaded*. Agreement among checks that share a blind spot is not corroboration.

## Measure the baseline before you attribute a delta

*2026-07-28*

**Symptom.** A page was rebuilt, and a check reported that loading it three times spawned one
stray console window. That is exactly the defect the rebuild was supposed to have fixed, so the
next half hour went into auditing every process-spawning call site in two large files. All of
them were already correct.

**What actually happened.** Nobody had measured what the counter did with **no page loads at
all**. Running that control took thirty seconds and returned: idle drift `delta=1`, three page
loads `delta=0`. The number was ambient background activity on the machine. The treatment arm
was clean the whole time — and the "regression" was an artifact of never having sampled the
null condition.

**The rule.** Before attributing a measured delta to your change, **measure the same quantity
with the change not exercised.** If the metric moves on its own, your delta is noise until
proven otherwise. This is cheap, it is skipped almost every time, and it is skipped hardest when
the number confirms what you already suspect.

**Why it generalises.** A metric that drifts is indistinguishable from a metric that responds,
unless you have looked at it idle. Confirmation is where controls feel least necessary and are
most load-bearing — you run them when the answer is surprising, and the answer that needs them
is the one that isn't.

---

## Any quantitative claim needs its comparability and its reach stated

*2026-07-28*

**Symptom.** Two conclusions were reported in one session, with correct arithmetic and clean
tables: an improvement with "the confound excluded", and "the same subject appears on both sides,
so this is controlled". Both were wrong. The confound was not excluded. The subject dominated the
*whole* dataset but had **zero** observations in the *subset* actually being compared — where one
side was seven subjects over two weeks and the other was one subject on one day.

**What actually happened.** No measurement was faulty. Every number was real. What was missing
was one sentence about whether the two groups differed *only* in the thing being tested, and how
far the conclusion was allowed to travel. Absent that sentence, a correct number over two
non-comparable populations reads exactly like a finding.

**The rule.** Every analysis states two things explicitly, in a fixed shape so it can be checked:
**internal validity** — what else differs between the compared groups (subject, day, build,
traffic mix, sample size) — and **external validity** — what population and window the claim
covers. "Uncontrolled, scoped to this subject and this window" is a complete and respectable
answer. Silence is not, because silence reads as "controlled".

**Why it generalises.** Analysis output is consumed as a conclusion, not as a dataset. Whoever
reads it cannot see the sampling unless you describe it, so an unstated comparability problem is
invisible by construction — and the arithmetic being right is what makes it persuasive. Enforced
here by [`mechanisms/hooks/data_validity_statement.py`](../mechanisms/hooks/data_validity_statement.py).

---

## A directory listing's timestamp is not the file's contents

*2026-07-28*

**Symptom.** A long-running daemon looked dead: its process existed, but a listing showed its log
file last written 26 hours earlier, despite work having arrived since. The diagnosis being drafted
was "alive but hung — a process that exists and does nothing".

**What actually happened.** Reading the *file* showed entries from minutes earlier. The daemon was
fine. Directory metadata is not flushed for a file held open with buffered writes, so the listing's
modified-time can lag the contents by hours on some platforms. The listing was stale, not the log.

**The rule.** When a timestamp is your evidence that something stopped, **open the artifact and
read the end of it.** Metadata about a file is a different observation from the file, and for
anything currently being written the metadata is the less reliable of the two.

**The generalisation worth keeping.** This is the same shape as judging a mutation by its exit
code rather than its postcondition, one level out: a cheap proxy standing next to the real
evidence, agreeing with it most of the time, and diverging exactly when something is actively
happening.

---

## A ratchet against a moving reference measures the reference

*2026-07-28*

**Symptom.** A drift check compared a stale copy of a generator against its upstream and reported
the copy had "worsened" from 58 to 66 functions behind — within an hour, while nobody had touched
the copy at all.

**What actually happened.** The check ratcheted on a *count*: "fail if the number of upstream
functions missing from the copy exceeds the recorded baseline of 58." But the upstream was live,
and its author shipped 8 new functions that afternoon. The gap grew by exactly those 8. The copy
was byte-identical to when the baseline was recorded. The metric moved entirely because the
*reference* moved, and it would have gone red every time the upstream was healthy and active —
i.e. the alarm fires hardest precisely when nothing is wrong.

**The rule.** A ratchet needs a fixed reference. Before pinning a baseline, ask **what happens to
this number when the thing I am comparing against changes and my subject does not.** If the answer
is "it moves," you have not built a ratchet, you have built a subscription to someone else's commit
rate. Either pin the reference (compare against a specific commit), ratchet on a *set* of named
items rather than a count, or — when the debt is known and a rebuild is already scheduled — make it
**informational and never failing**. A check that is red by construction gets muted, and "muted"
and "nobody looked" are the same state.

**Why it generalises.** Any metric of the form "distance from X" inherits X's volatility. Coverage
deltas against a moving main, lint-debt counts against an evolving ruleset, dependency lag against
an upstream release cadence, "N behind" for a fork — all have this shape. The failure is quiet
because the number is genuinely correct; it just is not measuring the thing whose name it carries.

## The renderer worked while every writer was dead

*2026-07-28*

**Symptom.** A status page rendered perfectly — correct data, no errors, freshly rebuilt hours
earlier. Every command-line tool that *wrote* to that page crashed on every invocation. Nobody
noticed until a human asked why his messages were not being answered.

**What actually happened.** The page generator had been replaced wholesale with a copy of a sibling
project's generator. The new copy inlined a helper the old one exported (`read_jsonl`), renamed a
path constant (`REPLIES` → `REPLIES_FILE`), and dropped a slug function. The writer CLIs imported
all three from the generator, treating it as the single source of truth for paths — good design,
and exactly what made them break together. Reads went through the new code; writes went through
the old API. The rebuild was verified by checking that **the page rendered**, which exercised zero
percent of the writer path.

**The rule.** When you replace a module wholesale, the postcondition must cover **every consumer of
its API, not just the one you were looking at**. Enumerate importers (`grep` for the module name
and for `module.attr` uses) and *run* each one, rather than reasoning that they are fine. Reads and
writes fail independently and asymmetrically: the read path is usually the one being demoed, so it
is the one that gets verified, while the write path fails silently until someone tries to use it.

**Why it generalises.** Any wholesale swap — a vendored library bump, a generated-client
regeneration, a rewrite behind a "same interface" claim — creates this asymmetry. The visible
surface keeps working, which actively suppresses investigation. Ask specifically: *what writes to
this thing, and when did I last run one of those?*

## A missing value satisfies a negative assertion, so the check goes green for the wrong reason

*2026-07-28*

**Symptom.** A freshness-check system re-runs each claim's premise and marks the ones that no
longer hold. A new check kind read a field out of a JSON response and compared it to an expected
value, with a flag saying whether the claim needed that comparison to be true or false. Asserting
*"this field is NOT X"* against a response where **the field did not exist at all** reported
HOLDS — a green, confident verdict resting on a field nobody could find.

**Why it is not a typo.** "Field ≠ X" is *vacuously true* when the field is absent, so the code was
correct and the answer was worthless. This is the same shape as `assertNotIn(x, collection)`
passing against an empty collection, a filter that matches nothing reporting "no violations", and a
policy check that finds no resources concluding compliance. Positive and negative assertions are
**not symmetric under missing data**: absence is real evidence against "it is X" and no evidence at
all about "it is not X".

**The rule.** Wherever a predicate can be asserted in both directions, decide what a **missing
operand** means *separately for each direction*, and make the answer for the negative direction
"I could not observe that" rather than a pass. If your system has a third outcome for instrument
failure — could-not-check, inconclusive, skipped — this is what it is for. If it does not have one,
that is the actual bug: a two-valued verifier will always resolve "I do not know" into whichever
answer the code path falls through to.

**How it was caught, which is the transferable part.** The positive control and the negative control
were run **side by side in one command**, not one at a time. Run alone, the negative case printed
`HOLDS` and looked exactly like success. Run beside its sibling, the *detail strings* were
identical — both said "there is no such field" — while the verdicts differed. The contradiction was
visible only in the diff between two results, never in either result on its own. The same run also
caught a second bug in the same draft: a byte cap set to a round 1,000,000 against a real payload
of 1,081,668 B, which turned every check against that endpoint into a silent could-not-check.

**Why it generalises.** Any system that grades claims — test assertions, lint rules, policy
engines, alert conditions, monitoring queries — eventually gets asked to assert a *negative*. That
is precisely where an empty result set and a satisfied condition become indistinguishable, and
where the grader is most likely to be trusted because it is green.

## A best-effort shim that always exits 0 turns a hard failure into permanent data loss

*2026-07-29*

**Symptom.** Two devices had firmware images nobody could reproduce. One board's crash dumps were
permanently undecodable — no debug symbols archived for the build it was running. Another board
showed a 29 KB memory regression that could not be attributed, because the image it replaced could
not be rebuilt. Both looked like process neglect: somebody forgot to archive.

**What actually happened.** Nobody forgot. A post-build hook uploaded the symbols on *every* build,
the server **rejected every upload** with a 400, and the hook ended in a bare `exit 0`. The
rejection was real and even printed — into build output nobody reads — and the build reported
success. The rejection itself was correct: the version string exceeded a hard field limit imposed
by the target's firmware header, and the server refused rather than silently truncate an identifier
used for update comparison. So a well-designed refusal, a well-intentioned best-effort uploader, and
a log nobody tails combined into months of silent, unrecoverable loss.

**Why the "best-effort" framing is the trap.** `exit 0` was deliberate: the author did not want a
symbol-upload failure to break a build. That instinct is right and the implementation inverts it.
The cost of a failed upload is not paid at build time — it is paid weeks later, by whoever needs the
symbols and no longer can get them. Best-effort is only honest when the effort's *failure* is
cheap. Here it was catastrophic and deferred, which is the worst combination: nobody feels it when
it happens, and nobody can fix it when they do.

**The rule.** For any side-effect whose failure is discovered *later than* the run that caused it,
`exit 0` on failure is not resilience — it is data loss with a success message. Either fail the
operation, or make the failure impossible to ignore at the point where the artifact is *consumed*
rather than produced. The gate that finally caught this refused to *flash* an image whose symbols
were not archived, which is the right layer: the consumer of the guarantee, not the producer.

**Ask this of every "best effort" path:** *who finds out, and when?* If the answer is "someone else,
much later, when it is too late to fix", the path needs to fail loudly now. A corollary worth
stating separately: **printing an error and exiting 0 is indistinguishable from success to every
automated caller**, and automated callers are the only ones that exist in a build pipeline.

**Why it generalises.** Retry wrappers that give up quietly, telemetry uploads that drop on 4xx,
cache warmers, backup jobs, index rebuilds, log shippers — all of them are usually written
best-effort, and all of them have the same shape: the failure is invisible at the time and
expensive at consumption. The absence of the artifact is the only evidence, and absence is exactly
what nobody checks.
## The tool computed the finding, then threw it away before printing

*2026-07-29*

**Symptom.** A live infrastructure audit reported `PASSED`. The report object it had just built
said `overall_status: "fail"` and carried a high-severity finding — a backup heartbeat 102 hours
stale against a 25-hour threshold. Both statements came from the same function call, seconds apart.
Nobody had been lied to by a stale cache or a skipped check: the check ran, found the problem, and
the problem never reached a human.

**What actually happened.** The test collected findings from two sources — a main evaluator and
some supplemental remote checks — and merged them into one report. Its print statements covered
only the *supplemental* branch, because that branch had been added later and the author printed
what he had just written. The main report was never rendered. Separately, the assertion that would
have failed on a blocking finding was gated behind an opt-in flag that operators did not pass. So
the run's exit status answered "did the test execute" and its output answered "what did the
supplemental checks say," and neither question was the one anyone was asking.

**The rule.** **A diagnostic's output is part of its contract, not a convenience.** When a tool
computes a judgement and then prints a subset of it, the unprinted part does not exist. Verify the
output surface the way you would verify a return value: make it emit the whole judgement, state the
overall verdict explicitly, and say *"no findings"* out loud rather than printing nothing — because
an empty output and a healthy result are the same pixels. Corollary: if the strict assertion is
behind a flag, the un-flagged path must still *report* loudly, or the flag becomes the only thing
that works and the default becomes decoration.

**Why it generalises.** This is the cheap-green failure with a new disguise: not a stale cache, not
a check that could not run, but a check that ran correctly and was silently truncated at the
presentation boundary. It appears wherever computation and reporting are separated — linters that
summarise only the first category, CI steps that echo one of several result files, dashboards that
render the panel someone was debugging. The tell is cheapness: a "full audit" that finishes in
eight seconds, a report with one line when the system has many subsystems. **Suspicion of a cheap
green is the highest-yield detector available**, because the alternative — trusting it — costs
exactly as much attention as a real outage would have, and buys nothing.

**Second-order.** The instrument here was the *audit framework itself*: the tool the estate uses to
detect this class of failure had the failure. Periodically point your verification discipline at
your verification tooling, because nothing else will.

## An instrument that scopes itself by "most recent" is correct only while you are alone

*2026-07-29*

**Symptom.** A pacer that fires periodically to keep a long agent run honest also reports the
run's context usage, because context exhaustion is what ends a run and the agent has no internal
sense of it. It announced **"context 58%"**. The session was actually at **23.0%** — 229,697
tokens of a 1M window, confirmed independently. The threshold for starting a wind-down was 60%.
One more turn and a run with three quarters of its window left would have begun shutting down on
a number belonging to something else.

**Cause.** Two readings — context used, and how long since the human last spoke — each located
"this session's transcript" as *the most recently modified transcript file on the machine*. That
expression is correct exactly when one session is running. Two were. It had been reading the
other session's numbers for the whole run, including a "human last spoke 0 min ago" for a human
who had not spoken in this session at all.

**Why it survived review.** The expression is not obviously wrong; it is *conditionally* right,
and the condition — being the only session — is invisible, ambient, and usually true. Nothing
about a wrong answer looks different from a right one: same shape, same units, plausible
magnitude. A sibling tool on the same box already handled this correctly, refusing with an
`AMBIGUOUS` error when it could not tell which session was meant, so the correct behaviour was
sitting ten metres away and was not copied.

**The rule.** **Identity, not recency.** Any instrument reporting on "this X" must select X by
identifier, and when no identifier is available and the choice is genuinely ambiguous, it must
**return nothing rather than pick**. The identifier usually already exists — here the harness
exports a session id into every tool subprocess, so the process was carrying its own answer the
whole time.

**The refusal branch is the part to test.** Selecting correctly when the id is present is the easy
half and it is what you will naturally check. Run the other one deliberately: strip the id, put
two candidates in play, and confirm you get nothing back. An instrument that degrades to guessing
under exactly the conditions that make guessing wrong is worse than one that never worked, because
its output is trusted at precisely the moment it stops being trustworthy.

**Second-order, and the reason this belongs here rather than in a changelog.** The same function
already carried a comment recording an earlier wrong-context-percentage incident, ending with *"a
wrong context % is worse than no context %: it is acted on."* The lesson had been learned, written
down, and placed at the exact site of the recurrence — and it did not prevent the second instance,
because it was a warning about a *value* and the new defect was in *scope selection*. A prose note
at the scene of the crime is not a control. When a class of failure repeats, replace the note with
a structural refusal.

## "Cannot be reproduced" is not "does not exist"

*2026-07-29*

**Symptom.** Three crash dumps from an embedded board could not be symbolicated: the server had no
debug binary matching the dumps' build hash. The build had come from a dirty working tree, so a
rebuild from the same commit could not produce a byte-identical binary. Two separate people wrote
the evidence off as permanently lost, and one of them — me — resolved the tracking card agreeing,
on the argument that *a dirty tree is not reconstructible by definition*.

That argument is correct. It also answers a question nobody asked. It is about **rebuilding** the
artifact; the question was whether the artifact still **existed**. It did, in an old build
directory, the whole time. Hashing every candidate binary on the machine — 54 of them, one command
— found the match immediately.

**Why the wrong answer was so comfortable.** It was *rigorous*. It cited a real property of the
build system, it was stated in the vocabulary of reproducibility, and it produced a confident
negative. A hand-wavy guess would have invited a check; a well-reasoned one closed the question.
**A sound argument about the adjacent question is more dangerous than no argument**, because its
soundness is what stops the search.

**The rule.** When you conclude something is unrecoverable, state which of these you actually
established, and notice if it is not the second:

1. it cannot be **regenerated** — a claim about a process;
2. it does not **exist anywhere** — a claim about the world, which needs a search.

Only (2) justifies giving up, and (2) is almost always cheap to test: the artifact has an
identifier (a hash, an id, a filename), so enumerate the candidates and compare. Minutes, and it
either recovers the evidence or upgrades the claim from an inference to a measurement.

**Generalises past build artifacts.** The same conflation retires a deleted record because the
source system has moved on, a log because the process that emitted it is gone, a dataset because
the pipeline changed. The producer being irreproducible says nothing about whether the output is
still lying around. See also the sibling failure in the other direction — a search that returns
nothing, read as an absence in the world rather than a fact about the search.

### Addendum, same instrument, one hour later: it was also reading its own echo

The pacer above had a second defect, found while confirming the first fix. Its
"how long since the human spoke" reading classified messages by SHAPE — a user-role entry
whose content is a plain string was taken as genuine input, versus a list-shaped one
(a tool result being fed back). That test is not sufficient, because the harness writes
several kinds of machine-generated message **in the user role with plain-string content**:
the wrapper that starts a scheduled run, every background-task completion notification,
turn-end hook feedback, injected system reminders.

Measured: the session's transcript held **six** such entries and **none was the human**.
One run-start wrapper, four task-notifications, one hook block. The person had not typed
anything in an hour.

**The shape of the failure is a feedback loop, and that is what makes it worth writing down.**
The pacer fires → its own completion notification lands as a user-role entry → the next read
reports "the human spoke 0 minutes ago" → the ladder stays on its tightest rung → it fires
again. The instrument was being driven by its own output, and it pinned itself to maximum
frequency *precisely when nobody was there* — burning the exact resource it exists to
conserve. Every individual reading was internally consistent; nothing looked wrong.

**Two rules.**

- **Classify by origin, not by shape.** Shape is a proxy for provenance and proxies drift as
  the platform adds message kinds. Match on the markers the machine actually emits.
- **When an instrument's own actions produce inputs to that instrument, say so explicitly and
  check the loop.** Self-observation is not automatically wrong, but it needs to be noticed —
  here nobody had, because the two roles (thing that fires, thing that measures quiet) lived
  in one file and looked unrelated.

**And a note on the fallback, which is where the first instinct is wrong.** With every entry
filtered out there is nothing left to timestamp, and the tempting answer is "unknown". It is
not unknown: no human message anywhere in the transcript *is* the measurement — the person has
been silent since the session began. Falling back to the session's own start time turns a
discarded null into a real number, and it is the one that lets the interval stretch honestly.

**Caveat worth carrying with the fix:** stretching the interval is only safe because a
separate always-armed watcher notifies within a second when the human does write. Fix the
measurement and lengthen the interval on the strength of it, and you have quietly made the
pacer the sole listener again — which is the failure this system had already paid for once.

## A claim's HOME decides whether it rots

*2026-07-29*

**Symptom.** An agent read a fact out of a project's own documentation, believed it, and used it to
correct the human about his own hardware. The human was right; the document was nine days out of
date. The maintained source — a separate reference the project keeps current — had retracted that
exact claim, with a dated note, more than a week earlier.

**What actually happened.** The project had **two homes for the same class of fact**, and only one of
them was maintained. A living reference gets corrected when reality changes. A document that *quotes*
that reference is a snapshot: correct on the day it was written, silently diverging every day after,
and **indistinguishable from current** because staleness has no visual signature. The snapshot even
looked *more* authoritative to an agent, because it was in the repo, in the working tree, one grep
away — while the maintained source needed a deliberate detour to reach.

**Why the usual defences miss it.** Nothing was wrong at the moment of writing, so review would have
passed. No test covers prose. The fix that corrected the maintained source had no reason to know the
snapshot existed, and no mechanism connected them. The failure is not that someone wrote something
wrong; it is that **a correct copy was made and then diverged**, which is the ordinary fate of every
copy.

**The rule.** For any class of fact, name the single maintained home, and make every other mention
**point** rather than **restate**. When you catch yourself copying a fact between documents, you are
creating a future contradiction with an unknown expiry — copy the pointer instead. And when a
maintained source and a local document disagree, the maintained one wins by default, without
argument; the local one is evidence about the past.

**The cheap structural version, which is what actually fixed it:** the entry-point document — the
one every agent reads before starting — named several code repositories and *no* reference
documentation at all. Adding a short table of "for facts of this kind, read this" costs nothing per
run and removes the incentive to re-derive. Re-derivation is the real cost: it is slow, it looks like
diligence, and it reproduces whichever stale copy it happens to land on.

**Why it generalises past documentation.** Any duplicated fact has this shape — a constant hardcoded
in two services, a schema restated in a client, a threshold repeated in an alert and a runbook, a
version pinned in three manifests. The question is never "is this right?" but "**is this the home, or
a copy of the home?**" A copy is not wrong; it is *unowned*, and unowned facts drift toward wrong at a
rate nobody is measuring.

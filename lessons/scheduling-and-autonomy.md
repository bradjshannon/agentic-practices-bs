# Scheduling and autonomy

## An agent that schedules its own successor can make itself invisible

*2026-07-21*

**Symptom.** A long-running autonomous agent had been operating on real servers for hours —
committing, patching a live host, opening and closing work items. Its operator could not find
the session anywhere in the desktop client: not in the session list, not under any recurring-job
entry. He only discovered it existed because it happened to be *waiting on a question*, which
surfaced it in a transient "needs input" strip on a welcome screen. Had it not been blocked, it
would have run to completion entirely unseen.

**What actually happened.** The agent framework offered two ways to schedule work:

- a **persistent recurring job** (a cron-style schedule on a named, always-enabled task), and
- a **one-shot job** that fires once at a timestamp and then **disables itself**.

A wind-down routine instructed each run to "schedule your successor" by creating a **new
one-shot job** for the next run. That worked — the successor fired on time. But because each
successor was a *freshly-created, self-disabling, uniquely-named* job, it was not a run of any
persistent recurring job. The client's UI groups runs under their parent recurring job; a
one-shot that has already fired is disabled and belongs to nothing, so it appears in no list.
The agent had effectively scheduled itself into a blind spot, once per run, forever.

Worse, it was self-perpetuating: each run's wind-down minted the next invisible run. Nobody
chose this; a wind-down checklist inherited from a different project said "schedule the
successor," and it silently contradicted the operator-facing contract, which said runs were
started manually.

**The rule.**

- **Recurrence belongs to one persistent, always-enabled job — never to a per-run throwaway.**
  An agent must not create a new scheduled task for its own successor.
- **To self-schedule, mutate the schedule of the job you already are** — rewrite that one
  persistent job's recurrence to encode your chosen next moment. Do not switch it to a one-shot:
  a one-shot fire disables the job, dropping it out of the operator's UI mid-run *and* ending the
  chain permanently if that run dies before it can re-arm.
- Keep a real recurrence (not a single date) as the **fail-safe**, so a run that crashes before
  re-scheduling cannot silently end the series.
- **If a human is meant to be able to interrupt an agent, verify they can actually see it**, from
  the surface they actually use. "It ran successfully" and "the operator could find it" are
  different claims.

**Why it generalises.** Any system with both "recurring job" and "run once at time T" primitives
has this trap, because the one-shot is usually the easier API for "do this again later." The
observability of a run is a property of *how it was scheduled*, not of what it did — and that
coupling is invisible until someone goes looking for a run and cannot find it.

---

## Let the agent choose its next run time, but make the choice explicit

*2026-07-21*

**Symptom.** A fixed daily schedule meant the agent woke on a timer regardless of whether there
was anything it could actually do. Most open work was blocked awaiting human decisions, so runs
either idled or invented low-value work to justify the wake-up.

**What actually happened.** Cadence was a hard-coded constant chosen once, by someone who could
not know the future state of the queue. The agent had strictly more information at wind-down
about when it should next run than the person who set the schedule ever did.

**The rule.** At wind-down, the agent picks its own next run time from **trigger factors** and
writes that choice into its own schedule, with the reasoning recorded. Useful factors:

- Is anything actionable *without* a human? If everything is blocked on a person, wake later.
- Is there an in-flight or degraded state that decays (an ephemeral patch, an expiring token, a
  running deploy)? Wake before it matters.
- Is there an external event to observe (a scheduled build, a rollout window)? Align to it.
- Is a human likely to be present to interact? If the run's value depends on being steerable,
  schedule it when someone is actually there.

State the chosen time **and the reason** in the handoff. A cadence nobody can explain reverts to
a default within two hands-offs.

**Why it generalises.** Self-scheduling converts a guess made once into a decision made with
current information, every cycle. The failure mode it replaces — a fixed timer firing into an
empty queue — is one of the most common ways autonomous systems burn budget while looking busy.

## The wake-up mechanism gets dropped exactly when it looks redundant (2026-07-22)

**Symptom.** An unattended run sat **idle for 7.1 hours** — measured from its own hook log,
04:02 → 11:09 — and neither the agent nor the operator noticed until the operator asked what
had been accomplished. Nothing crashed. Nothing wedged. The run had simply stopped.

**What actually happened.** An agent is re-invoked by exactly two things: a message from the
human, or a background task completing. A self-scheduled timer ("the pacer") exists precisely to
guarantee the second one. It had been armed repeatedly through the early part of the run — and
then arming lapsed, and the run's last timer fired at 03:21 with nothing armed after it. When
the human stopped messaging, nothing remained that could wake the agent.

The reason it lapsed is the whole lesson, and it is not carelessness: **arming stopped while the
human was actively conversing.** Every reply was waking the agent anyway, so re-arming felt
redundant on each individual turn — and the judgement was locally correct every time. The
mechanism was abandoned exactly when its perceived value was lowest, which was immediately
before it became the only thing that could wake the run.

**The rule.** Any control whose perceived value is **lowest right before it is needed** cannot
be left to judgement, no matter how well understood it is. Note that this run's own standing
instructions already described the timer as "the backstop for the yield-and-stall failure" — it
was documented, understood, and dropped anyway.

The enforceable form: refuse to end a turn when nothing is scheduled to wake the run. A hook
cannot arm the timer itself — what re-invokes the agent is the completion of a task the *agent*
created — but it can block the turn from ending unarmed, which converts "remember to re-arm"
into "the turn does not end until you have."

Make *armed* a **timestamp, not a flag**: record when the timer will fire, and treat a time in
the past as unarmed. A killed or already-fired timer then reads as unarmed automatically, so
there is no stale state that can rot into a false "yes, something will wake you," and no cleanup
step to forget. (`mechanisms/hooks/pacer_armed.py`.)

**Why it generalises.** This is the general failure of any safety net used by a system that
usually has another one: the redundant path atrophies while the primary is healthy, and its
absence is discovered only when the primary stops. The specific agent version is nastier than
most, because an idle agent produces no error, no log line, and no alert — the failure's only
symptom is silence, and silence is what a working agent looks like between turns.

## A background worker can die silently — no completion signal ever arrives (2026-07-24)

**Symptom.** An agent dispatched a background sub-worker, then reported "still running" for over an hour. The worker had in fact terminated almost immediately, having produced nothing — and no completion event was ever delivered.

**What actually happened.** The dispatch model delivers a completion event when a worker *finishes cleanly*. A worker that dies — wedges, is killed, hits a terminal error on resume — may emit no event at all, so "no notification yet" is indistinguishable from "still working." The parent waited on a signal that would never come, and kept telling the operator the wrong thing.

**The rule.** Never infer a background worker's liveness from the *absence* of a completion signal. Check its externally observable state — commits on its branch, output-file growth, working-tree mtimes — and treat "created its workspace but no progress for a long interval" as dead, not slow. When you stop one, verify it actually stopped: a stop call that reports "no such task" means it was already gone, which is itself the answer.

**Why it generalises.** Any system that signals success but not silent death has its blind spot exactly where you most need visibility — the failure case. A liveness check must observe the *work*, not the *notification*, for the same reason a green status endpoint is not proof of the capability behind it.

## A scheduled task pointed at an ephemeral working directory is a silent time bomb (2026-07-27)

**Symptom.** A recurring task (poll three servers, write a health snapshot to each) had been firing every two minutes for weeks and reporting a clean exit — yet the file it wrote had been frozen with a 17-day-old timestamp on every target. Downstream dashboards read that file and showed 17-day-old health as current. Nobody noticed, because a stale file is byte-identical to a fresh one.

**What actually happened.** The task's *working directory* had been set to a **per-session git worktree** — an ephemeral checkout created for one agent session. The task invoked its script by a **relative** path from that cwd. Later, that worktree was switched to a different branch that did not contain the script (worktrees are cheap and get reused, switched, sparse-checked-out, and deleted). The script vanished from the cwd; the task began exiting with file-not-found; and because the operator only ever looked at "did it run" (exit status) and not "did the output change" (the postcondition), the dead task looked healthy for 17 days. The exit code answered "did the command run," never "did the write land."

**The rule.** A scheduled/cron task must never anchor its working directory or script path to a per-session worktree, a temp dir, or any path whose existence and contents are not guaranteed for the life of the schedule. Point automation at a stable, always-present location and prefer an **absolute** script path so a wrong cwd cannot silently break it. And judge the task on its **postcondition** — read the output back and assert it changed — not on exit code; a task whose output can freeze while it keeps exiting 0 has no working health signal at all.

**Why it generalises.** Ephemeral-by-design workspaces (worktrees, containers, scratch dirs, tmpfs) are everywhere in agent tooling, and a long-lived schedule outlives any one of them. The moment a durable job binds to a disposable path, its correctness depends on something explicitly built to be thrown away — and the failure surfaces as silence, the exact shape (a green/stale signal standing in for the capability) that is hardest to catch and most expensive when missed.

## Creating the successor can freeze the run that creates it — 5.5 hours, measured (2026-08-10)

**Symptom.** A headless agent run followed its own contract — *"every run schedules its own successor, at prime, with a conservative fire time"* — and called the scheduling tool. The call raised a **UI authorization card** in the desktop app. From that moment nothing in the run executed: no tool call, no scheduled wake-up, no reconciliation of the five subagents it had dispatched. It resumed only when the operator noticed the card and cleared it, **5 hours 38 minutes later**. The operator's words: *"it popped up an auth card in the UI, which block all of your operations until I saw it this morning."*

**What made it worse than a plain block.** The call had *also* failed argument validation, so **no successor was ever created**. The run paid the full outage and got nothing for it. And the freeze is invisible from inside: an agent has no clock it can consult unprompted, so on resuming, six hours of wall time and six seconds look identical — the run's own heartbeat is one of the things the freeze suspends.

**The inversion that matters.** The reason to schedule *early* is fail-off: if the run dies at 60%, a successor already exists. But a call that can freeze the run **is itself the thing most likely to kill it**, and it fires at the moment of maximum remaining value. The mitigation and the hazard are the same call. Fail-off is not the failure mode any more; **fail-frozen** is, and unlike a crash it produces no artifact at all.

**Read-only calls in the same family did not trip it.** Listing the existing schedule ran twice in the same session with no card. So the boundary is create/modify, not the tool surface — which means the chain can still be *inspected* safely, and only the write needs a human.

**The rule.** Do not issue a state-creating call to a UI-mediated tool from an unattended run unless someone has established that its approval persists across sessions. Where the call is genuinely needed, prefer: (a) a read-only probe to confirm the state first; (b) doing it while a human is demonstrably present; or (c) declaring the gap — *"no successor is scheduled"* — in the handoff, so the missing link is a known state rather than a surprise. A gap somebody knows about beats a run that stopped existing.

**Why it generalises.** Any tool whose permission model can escalate to a human-in-the-loop prompt is a **synchronous dependency on human attention**, whatever its documentation implies. That is fine in an interactive session and catastrophic in an unattended one, where the human's response latency becomes the run's. Before automating a call, ask not only "may I do this?" but "what happens to everything else if the answer arrives in six hours?" — and note that the blocking behaviour is a property of the *harness*, not of the tool, so it will not appear in the tool's own contract.

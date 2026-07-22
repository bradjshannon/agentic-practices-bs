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

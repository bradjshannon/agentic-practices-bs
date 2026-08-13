# A subagent doing investigation work leaves no artifacts, so artifact-silence reads as death

**2026-08-13. Second instance of this class; the first was 2026-08-01.**

A conductor killed a healthy firmware agent. The evidence it reasoned from:

- 8 tool calls in 48 minutes
- no new git branch in the repo the lot was scoped to
- no `ninja` / `cmake` / compiler process running

All three are blind to the work the agent was actually doing: probing a running server's
endpoint to characterise a false-positive detector. That produces no commit, no branch, no
build process, and no file. The agent's dying words were mid-probe.

## The instrument that was available and was discounted

Two `SendMessage` probes had already come back **`Message queued for delivery at its next tool
round`** — the reply that only a *running* agent produces. The conductor read them as
bookkeeping. The 2026-08-01 instance recorded in the same project's brief did exactly this, and
the brief says so; reading that passage did not prevent repeating it.

`SendMessage` distinguishes three states non-destructively:

| the agent is… | the reply |
|---|---|
| running right now | `Message queued for delivery … at its next tool round` |
| finished / idle | `had no active task; resumed from transcript in the background` |
| previously killed | `was stopped (killed); resumed it in the background` |

Process state and repo state distinguish nothing, because whether they move at all depends on
what class of work the lot was given.

## What the artifact check is actually measuring

An artifact-based liveness check silently encodes an assumption about the lot's *output shape*.
It works for a build lot, a commit lot, a flash lot. It returns a confident false negative for:

- endpoint / API investigation
- log or transcript reading
- anything whose deliverable is a *conclusion* rather than a file

The conductor never noticed it had made that assumption, which is why the check felt like
evidence rather than like a guess.

## ⚠️ SECOND INSTANCE, SAME RUN, ~90 MINUTES AFTER THIS FILE WAS COMMITTED

The same conductor killed a second working agent. **It had followed this lesson's letter** — it
probed with `SendMessage` and received `Message queued for delivery at its next tool round`, the
reply that means *running*. It then went and collected artifact evidence anyway (a tool-call
marker frozen at 40 for 90 minutes, low CPU on every candidate process) and killed on that. The
agent's dying words were mid-work: five logging test cases passing, moving to the next site.

**So the rule above was not strong enough, because it names the wrong step.** The failure was not
skipping the probe. It was *continuing to gather evidence after the probe had already answered*,
and letting the weaker evidence win. That feels like diligence from the inside. It is looking for
permission.

**The stronger rule: the probe's answer is the verdict. Artifact evidence does not overturn it.**
Once `SendMessage` says running, the agent is running — a stale marker, an idle CPU and an empty
git status are all consistent with a long call and none of them is a second opinion. If you find
yourself assembling a case against a probe result you already have, stop: you have decided and are
now shopping for support.

One instrument fact that fell out, worth having on its own: **the per-agent tool-call marker can
freeze while an agent works.** It sat at 40 for 90 minutes across demonstrable activity. Do not
treat marker staleness as data about an agent at all.

## The rule

**A required milestone line that never arrives is the finding. Chase the missing milestone;
do not substitute an inference from artifacts.**

If a brief requires a milestone at each checkpoint — and any brief with a slow step should —
then its absence is a fact about the *reporting*, not about the agent, and the response is to
ask. Asking costs one non-destructive message. The alternative destroyed 48 minutes of live
work on a guess.

Damage was nil: `SendMessage` resumes a killed agent with its context intact, and the revived
agent continued from the same probe. That recoverability is the only reason this is a lesson
rather than an incident.

Related: `a-subagents-negative-is-not-evidence.md`,
`sendmessage-is-a-nondestructive-liveness-probe-2026-08-01.md`,
`instrument-silence-not-data-six-nulls.md`.
